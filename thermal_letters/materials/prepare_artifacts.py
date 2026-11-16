"""Extract notebook figures and simulate the room's transient temperature."""

import argparse
import base64
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def load_room_model(notebook):
    """Load only explicitly tagged model cells, without running plots or checks."""
    namespace = {"__name__": "thermal_notebook"}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code" and "room-model" in cell.get("metadata", {}).get("tags", []):
            source = "".join(cell["source"])
            exec(compile(source, "lab.ipynb:model-definitions", "exec"), namespace)
    required = ("build_heat_grid", "solve_room_heat", "room_neighbor_average")
    if not all(name in namespace for name in required):
        raise ValueError("The notebook is missing the required room functions.")
    return namespace


def explicit_step(grid, temperature, capacity, dt, neighbor_average):
    """Advance C*dT/dt = K*Laplacian(T) - H*(T-T_ambient)."""
    if not np.isfinite(capacity) or capacity <= 0:
        raise ValueError("Areal heat capacity must be finite and positive.")
    factor = dt * grid["diagonal"] / capacity
    if not np.isfinite(dt) or dt <= 0 or factor > 1 + 1e-12:
        raise ValueError("Time step violates the sufficient monotonicity condition.")
    result = temperature.copy()
    interior = result[1:-1, 1:-1]
    old = temperature[1:-1, 1:-1]
    average = neighbor_average(grid, temperature)
    free = grid["free"]
    interior[free] = old[free] + factor * (average[free] - old[free])
    return result


def sample_evolution(grid, steady, capacity, dt, neighbor_average, threshold=0.01):
    """Find the settling time, then keep uniformly sampled fields for the GIF."""
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("The settling threshold must be finite and positive.")
    temperature = grid["values"].copy()
    trace = [(0.0, float(np.max(np.abs(temperature - steady))))]
    # Save about 100 uniformly spaced physical times after finding the end time.
    steps = 0
    while trace[-1][1] > threshold:
        temperature = explicit_step(grid, temperature, capacity, dt, neighbor_average)
        steps += 1
        error = float(np.max(np.abs(temperature - steady)))
        trace.append((steps * dt, error))
        if steps > 100000:
            raise RuntimeError("The transient calculation did not reach the target tolerance.")
    selected = sorted(set(np.rint(np.linspace(0, steps, 101)).astype(int)))
    temperature = grid["values"].copy()
    frames = [temperature.copy()]
    selected_set = set(selected[1:])
    lower = min(float(grid["values"][grid["fixed"]].min()), grid["room"]["ambient"])
    upper = max(float(grid["values"][grid["fixed"]].max()), grid["room"]["ambient"])
    for step in range(1, steps + 1):
        temperature = explicit_step(grid, temperature, capacity, dt, neighbor_average)
        if step in selected_set:
            np.testing.assert_array_equal(temperature[grid["fixed"]], grid["values"][grid["fixed"]])
            assert temperature.min() >= lower - 1e-10
            assert temperature.max() <= upper + 1e-10
            frames.append(temperature.copy())
    return np.asarray(selected) * dt, frames, np.asarray(trace)


def verify_transient(grid, steady, capacity, dt, neighbor_average, build_grid, room):
    # A steady field is a fixed point of the transient operator.
    advanced = explicit_step(grid, steady, capacity, dt, neighbor_average)
    np.testing.assert_allclose(advanced, steady, rtol=0, atol=1e-8)
    uniform_room = dict(room, left=21, right=21, bottom=21, top=21, ambient=21)
    uniform = build_grid(uniform_room, 8, 6)
    actual = explicit_step(uniform, uniform["values"], capacity,
                           0.9 * capacity / uniform["diagonal"], neighbor_average)
    np.testing.assert_allclose(actual, 21, rtol=0, atol=1e-12)
    try:
        explicit_step(grid, steady, capacity, 1.1 * capacity / grid["diagonal"], neighbor_average)
    except ValueError:
        pass
    else:
        raise AssertionError("An unsafe time step must be rejected.")

    # Compare the same physical time using dt and dt/2.
    count = int(round(300 / dt))
    results = []
    for step_size, iterations in ((dt, count), (dt / 2, 2 * count)):
        field = grid["values"].copy()
        for _ in range(iterations):
            field = explicit_step(grid, field, capacity, step_size, neighbor_average)
        results.append(field)
    return float(np.max(np.abs(results[0] - results[1])))


def save_animation(grid, times, frames, steady, output, assets):
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=100)
    fig.patch.set_facecolor("#ffffff")
    lower = min(float(grid["values"][grid["fixed"]].min()), grid["room"]["ambient"])
    upper = max(float(grid["values"][grid["fixed"]].max()), grid["room"]["ambient"])
    image = ax.imshow(frames[0], origin="lower", extent=(0, grid["room"]["width"],
                      0, grid["room"]["height"]), cmap="inferno", vmin=lower, vmax=upper,
                      interpolation="bilinear", aspect="equal")
    ax.set(xlabel="x (m)", ylabel="y (m)")
    fig.colorbar(image, ax=ax, label="Temperature (deg C)", shrink=0.83)
    title = ax.set_title("Transient heat conduction", loc="left", pad=16)
    annotation = fig.text(0.11, 0.06, "", fontsize=11)
    fig.text(0.11, 0.025, "Illustrative model: C = 1000 J/(m^2 K); fixed-temperature heater surfaces",
             fontsize=9, color="#596575")
    fig.subplots_adjust(left=0.09, right=0.94, top=0.88, bottom=0.15)
    # A shared palette keeps the temperature colors consistent across frames.
    palette_colors = np.vstack([plt.get_cmap("inferno")(np.linspace(0, 1, 224))[:, :3] * 255,
                                np.repeat(np.arange(0, 256, 8)[:, None], 3, axis=1)])
    palette = Image.new("P", (1, 1))
    palette.putpalette(palette_colors.astype(np.uint8).ravel().tolist())
    rendered = []
    snapshots = {0: "transient_start", len(frames) // 2: "transient_middle", len(frames) - 1: "transient_end"}
    for index, (time, field) in enumerate(zip(times, frames)):
        image.set_data(field)
        title.set_text(f"Heat distribution in the room: t = {time:.0f} s")
        difference = np.max(np.abs(field - steady))
        annotation.set_text(f"Maximum difference from steady field: {difference:.3f} deg C")
        fig.canvas.draw()
        rgb = Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3])
        if index in snapshots:
            rgb.save(assets / f"{snapshots[index]}.png")
        rendered.append(rgb.quantize(palette=palette, dither=Image.Dither.NONE))
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = [90] * len(rendered)
    durations[0], durations[-1] = 700, 2000
    rendered[0].save(output, save_all=True, append_images=rendered[1:], duration=durations,
                     loop=0, optimize=False, disposal=2)
    plt.close(fig)
    with Image.open(output) as animation:
        assert animation.is_animated and animation.n_frames >= 100
    return len(rendered)


EQUATIONS = {
    "laplace": r"\nabla^2u=0,\qquad T=100u",
    "steady": r"-K\nabla^2T+H(T-T_a)=0",
    "stencil": r"\overline{T}_{j,i}=\frac{a_x(T_{j,i-1}+T_{j,i+1})+a_y(T_{j-1,i}+T_{j+1,i})+HT_a}{2a_x+2a_y+H}",
    "weights": r"a_x=K/\Delta x^2,\quad a_y=K/\Delta y^2,\quad d=2a_x+2a_y+H",
    "jacobi": r"T_i^{(k+1)}=\frac{b_i-\sum_{j\ne i}A_{ij}T_j^{(k)}}{A_{ii}},\qquad B_J=I-D^{-1}A",
    "gs": r"T_i^{(k+1)}=\frac{b_i-\sum_{j<i}A_{ij}T_j^{(k+1)}-\sum_{j>i}A_{ij}T_j^{(k)}}{A_{ii}}",
    "sor": r"T_i^{(k+1)}=T_i^{(k)}+\omega\left(\overline{T}_i^{GS}-T_i^{(k)}\right),\qquad 0<\omega<2",
    "convergence": r"e^{(k+1)}=Be^{(k)},\qquad \rho(B)<1",
    "optimum": r"\rho_J=\cos(\pi/n),\quad\rho_{GS}=\rho_J^2,\quad\omega_* =\frac{2}{1+\sin(\pi/n)}",
    "residual": r"r=b-AT,\qquad \eta=\Vert r/d\Vert_\infty,\qquad e=A^{-1}r",
    "bound": r"H>0:\qquad \Vert e\Vert_\infty\leq\frac{\Vert r\Vert_\infty}{H}",
    "fourier": r"u_L=\sum_{k=1,3,\ldots}\frac{4u_{left}}{k\pi}\sin\frac{k\pi y}{L}\frac{\sinh(k\pi(1-x/L))}{\sinh(k\pi)}",
    "length": r"\ell=\sqrt{K/H}=0.577\ \mathrm{m}",
    "transient": r"C\frac{\partial T}{\partial t}=K\nabla^2T-H(T-T_a)",
    "ftcs": r"T^{n+1}_{j,i}=T^n_{j,i}+\frac{\Delta t\,d}{C}\left(\overline{T}^n_{j,i}-T^n_{j,i}\right)",
    "cfl": r"\frac{\Delta t}{C}\left(\frac{2K}{\Delta x^2}+\frac{2K}{\Delta y^2}+H\right)\leq 1",
}


def prepare_assets(notebook, assets):
    assets.mkdir(parents=True, exist_ok=True)
    figure_number = 0
    for cell in notebook["cells"]:
        for output in cell.get("outputs", []):
            encoded = output.get("data", {}).get("image/png")
            if encoded:
                figure_number += 1
                (assets / f"figure_{figure_number:02d}.png").write_bytes(base64.b64decode("".join(encoded)))
    if figure_number != 11:
        raise ValueError(f"Expected 11 saved notebook figures, found {figure_number}.")
    for name, formula in EQUATIONS.items():
        fig = plt.figure(figsize=(13, 0.85), dpi=180)
        fig.text(0.02, 0.5, f"${formula}$", fontsize=24, color="#15283c", va="center")
        fig.savefig(assets / f"equation_{name}.png", bbox_inches="tight", pad_inches=0.08, facecolor="white")
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=ROOT / "thermal_letters/lab.ipynb")
    parser.add_argument("--assets", type=Path, default=ROOT / "tmp/pdfs/thermal_letters/assets")
    parser.add_argument("--output", type=Path, default=ROOT / "output/gif/thermal_letters.gif")
    args = parser.parse_args()
    notebook = json.loads(args.notebook.read_text(encoding="utf-8"))
    prepare_assets(notebook, args.assets)
    model = load_room_model(notebook)
    room = model["room"]
    heaters = (model["make_letter_heaters"](room, model["heater_temperature"], model["stroke_width"])
               if model["custom_heaters"] is None else list(model["custom_heaters"]))
    grid = model["build_heat_grid"](room, model["nx"], model["ny"], heaters, model["windows"])
    steady, _ = model["solve_room_heat"](grid, omega=model["omega"], tol=model["tolerance"])
    capacity = 1000.0  # Illustrative areal heat capacity, J/(m^2 K).
    dt = 0.9 * capacity / grid["diagonal"]
    temporal_difference = verify_transient(grid, steady, capacity, dt, model["room_neighbor_average"],
                                           model["build_heat_grid"], room)
    times, frames, trace = sample_evolution(grid, steady, capacity, dt, model["room_neighbor_average"])
    frame_count = save_animation(grid, times, frames, steady, args.output, args.assets)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.semilogy(trace[:, 0], trace[:, 1], color="#236a96")
    ax.axhline(0.01, color="#b74b1c", linestyle="--", label="0.01 deg C target")
    ax.set(xlabel="Simulation time (s)", ylabel="Maximum difference from steady field (deg C)",
           title="Transient approach to the steady field")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.assets / "transient_convergence.png", dpi=150)
    plt.close(fig)
    metadata = dict(capacity=capacity, dt=dt, time_end=float(times[-1]), frames=frame_count,
                    final_difference=float(trace[-1, 1]), temporal_refinement_difference=temporal_difference,
                    cfl=dt * grid["diagonal"] / capacity)
    (args.assets / "transient_results.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    print(f"Saved animation: {args.output}")


if __name__ == "__main__":
    main()
