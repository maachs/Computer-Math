"""Build the Russian PDF presentation from notebook evidence and simulation assets."""

import argparse
import json
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle


ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 960, 540
INK = colors.HexColor("#173247")
BODY = colors.HexColor("#263b4c")
MUTED = colors.HexColor("#647484")


def normalize_notation(text):
    replacements = {
        "10⁻⁹": "10<super>-9</super>", "10⁻⁸": "10<super>-8</super>",
        "10⁻⁶": "10<super>-6</super>", "r₀": "r<sub>0</sub>",
        "log₂": "log<sub>2</sub>", "Eₕ/Eₕ/₂": "E<sub>h</sub>/E<sub>h/2</sub>",
    }
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)
    return text


class SlideDocument:
    """Draw a fixed-size slide document with measured text and image placement."""

    def __init__(self, output, assets, font_directory):
        output.parent.mkdir(parents=True, exist_ok=True)
        self.assets = assets
        self.page = 0
        self.canvas = canvas.Canvas(str(output), pagesize=(WIDTH, HEIGHT), pageCompression=1)
        self.canvas.setTitle("Стационарная теплопроводность и тепловая надпись РТ")
        self.canvas.setAuthor("Лабораторная работа по вычислительной математике")
        for name, filename in (("Body", "arial.ttf"), ("Body-Bold", "arialbd.ttf"),
                               ("Body-Italic", "ariali.ttf")):
            pdfmetrics.registerFont(TTFont(name, str(font_directory / filename)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic")

    def text(self, text, x, top, width, size=16, height=400, color=BODY, bold=False):
        style = ParagraphStyle("slide", fontName="Body-Bold" if bold else "Body",
                               fontSize=size, leading=size * 1.32, textColor=color,
                               spaceAfter=0, allowWidows=0, allowOrphans=0)
        paragraph = Paragraph(normalize_notation(text), style)
        _, actual_height = paragraph.wrap(width, height)
        if actual_height > height + 0.2:
            raise ValueError(f"Slide {self.page}: text needs {actual_height:.1f} pt, available {height} pt: {text[:80]}")
        if top + actual_height > HEIGHT - 30:
            raise ValueError(f"Slide {self.page}: text extends past the footer.")
        paragraph.drawOn(self.canvas, x, HEIGHT - top - actual_height)
        return actual_height

    def paragraphs(self, paragraphs, x, top, width, size=16, gap=15):
        for paragraph in paragraphs:
            top += self.text(paragraph, x, top, width, size=size) + gap
        return top

    def image(self, filename, x, top, width, height):
        path = self.assets / filename
        with Image.open(path) as picture:
            scale = min(width / picture.width, height / picture.height)
            actual_width, actual_height = picture.width * scale, picture.height * scale
        self.canvas.drawImage(str(path), x + (width - actual_width) / 2,
                              HEIGHT - top - actual_height, width=actual_width, height=actual_height,
                              mask="auto")
        return actual_height

    def equation(self, name, x=48, top=122, width=864, height=67):
        return self.image(f"equation_{name}.png", x, top, width, height)

    def table(self, rows, x, top, widths, size=14, row_height=37):
        style = ParagraphStyle("table", fontName="Body", fontSize=size,
                               leading=size * 1.18, textColor=BODY)
        data = [[Paragraph(normalize_notation(str(value)), style) for value in row] for row in rows]
        table = Table(data, colWidths=widths, rowHeights=row_height)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 1, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#d4dce2")),
        ]))
        _, actual_height = table.wrap(sum(widths), HEIGHT)
        if top + actual_height > HEIGHT - 40:
            raise ValueError(f"Slide {self.page}: table extends past the footer.")
        table.drawOn(self.canvas, x, HEIGHT - top - actual_height)

    def start(self, title, subtitle=None):
        if self.page:
            self.canvas.showPage()
        self.page += 1
        self.canvas.setFillColor(colors.white)
        self.canvas.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        self.text(title, 48, 33, 864, size=29, height=80, color=INK, bold=True)
        if subtitle:
            self.text(subtitle, 48, 82, 864, size=13, height=40, color=MUTED)
        self.canvas.setFont("Body", 9)
        self.canvas.setFillColor(MUTED)
        self.canvas.drawString(48, 17, "Вычислительная математика. Теплопроводность")
        self.canvas.drawRightString(912, 17, f"{self.page:02d}")

    def source(self, text):
        self.text(text, 48, 493, 840, size=8.8, height=17, color=MUTED)

    def save(self):
        self.canvas.save()


def build(output, assets, font_directory):
    transient = json.loads((assets / "transient_results.json").read_text(encoding="utf-8"))
    deck = SlideDocument(output, assets, font_directory)

    deck.start("Стационарная теплопроводность")
    deck.text("Тепловая надпись<br/>«РТ»", 48, 135, 670, size=58, height=180, bold=True, color=INK)
    deck.text("Методы Якоби, Зейделя и SOR<br/>Применимость, сходимость и погрешности", 51, 344, 800,
               size=23, height=95)
    deck.text("Лабораторная работа №3<br/>Стационарные поля и динамика нагрева комнаты",
               51, 438, 820, size=14, height=45, color=MUTED)

    deck.start("Две задачи одной работы", "Данные исходной лабораторной и геометрия комнаты")
    deck.paragraphs([
        "<b>Квадрат</b><br/>L = 0.1 м. Слева u = 1, сверху 2, справа 3, снизу 4. Температура T = 100u.",
        "<b>Комната</b><br/>10 × 6 м. Стены: слева и справа 18 °C, снизу 16 °C, сверху 20 °C.",
        "Обогреватели 65 °C. Два окна по 5 °C. Шесть полос образуют «РТ». Начальная среда 18 °C.",
    ], 48, 123, 327, size=16)
    deck.image("figure_06.png", 400, 116, 512, 365)
    deck.source("Источник: lab.ipynb, параметры и ячейка 33. Размеры оборудования заданы в метрах.")

    deck.start("Физическая модель и её допустимость")
    deck.equation("laplace", 48, 117, 330, 60)
    deck.equation("steady", 470, 117, 390, 60)
    deck.paragraphs([
        "<b>Квадрат</b><br/>Однородная среда, постоянная теплопроводность. Внутренних источников нет. На границе задана температура.",
        "<b>Комната</b><br/>K = 1 Вт/К для слоя, H = 3 Вт/(м²·К), Tₐ = 18 °C. Через пол и потолок идёт распределённый теплообмен.",
    ], 48, 204, 400, size=16)
    deck.paragraphs([
        "<b>Граничные условия Дирихле</b><br/>Стены, окна и нагреватели сохраняют свои температуры. В углах внешней границы берём среднее соседних стен.",
        "<b>Область применимости</b><br/>Учебная модель теплопроводности. Для реальной комнаты нужны конвекция, трёхмерная геометрия и мощность приборов.",
    ], 490, 204, 420, size=16)
    deck.source("Вывод из модели работы. H обозначает коэффициент room['heat_loss'], Tₐ = room['ambient'].")

    deck.start("Разностная схема и свойства системы")
    deck.equation("stencil", top=117, height=70)
    deck.equation("weights", top=203, height=45)
    deck.paragraphs([
        "После исключения фиксированных узлов получаем <b>AT = b</b>. Матрица симметрична, её диагональ положительна, внедиагональные элементы неположительны.",
        "При K &gt; 0 и H ≥ 0 энергия состоит из сумм квадратов разностей соседних значений и вклада H. Связь каждой свободной компоненты с границей Дирихле даёт <b>A &gt; 0</b>.",
    ], 48, 277, 419, size=15.5, gap=14)
    deck.paragraphs([
        "При H &gt; 0 диагональное преобладание строгое. При H = 0 оно может быть нестрогим, но связь с фиксированными узлами обеспечивает единственность решения.",
        "Поэтому для этой сетки допустимы Якоби, Зейдель и SOR. Все они решают одну систему. Порядок обхода меняет промежуточные итерации.",
    ], 493, 277, 419, size=15.5, gap=14)
    deck.source("Свойства выведены для положительных коэффициентов пятиузловой схемы и фиксированных температур данной работы.")

    deck.start("Метод Якоби", "Все новые значения используют предыдущую итерацию. D = diag(A) есть диагональная часть матрицы")
    deck.equation("jacobi", top=126, height=77)
    deck.equation("convergence", 48, 224, 430, 48)
    deck.paragraphs([
        "<b>Условие сходимости</b><br/>Для любого начального приближения необходимо и достаточно ρ(Bⱼ) &lt; 1. Здесь ρ есть максимальный модуль собственного значения матрицы итерации.",
        "Строгое диагональное преобладание достаточно. В нашей сетке с H = 0 сходимость обеспечивает структура разностного оператора и закреплённая граница.",
    ], 48, 294, 419, size=15.5, gap=13)
    deck.paragraphs([
        "<b>Достоинства</b><br/>Простая реализация. Узлы независимы внутри шага, поэтому обновление легко распараллелить.",
        "<b>Ограничения</b><br/>Медленная сходимость на мелкой сетке. Симметричная положительная определённость произвольной матрицы сама по себе не гарантирует сходимость Якоби.",
    ], 493, 235, 419, size=16, gap=19)
    deck.source("Теория: Netlib Templates, разделы The Jacobi Method и Convergence of the Jacobi method [1, 2].")

    deck.start("Метод Зейделя и шахматный обход")
    deck.equation("gs", top=119, height=80)
    deck.paragraphs([
        "<b>Последовательный Зейдель</b><br/>В квадрате используем уже обновлённые левый и нижний узлы. Каждое новое значение сразу участвует в следующем вычислении.",
        "<b>Шахматный Зейдель</b><br/>В комнате сначала обновляем один цвет сетки, затем другой. Узлы одного цвета не являются соседями по шаблону.",
    ], 48, 233, 419, size=16, gap=21)
    deck.paragraphs([
        "<b>Условия</b><br/>Ненулевая диагональ нужна для шага. SPD-матрица или строгое диагональное преобладание гарантируют сходимость.",
        "Оба обхода допустимы для нашей SPD-системы. Порядок меняет скорость, но предельное решение совпадает. Шахматный обход удобен для NumPy.",
    ], 493, 233, 419, size=16, gap=21)
    deck.source("Теория: Netlib Templates, The Gauss-Seidel Method [3]. Обходы соответствуют двум реализациям в lab.ipynb.")

    deck.start("Метод верхней релаксации SOR")
    deck.equation("sor", top=124, height=75)
    deck.paragraphs([
        "<b>Как устроен шаг</b><br/>Вычисляем значение Зейделя и сдвигаемся к нему с множителем ω. При ω = 1 получаем Зейделя. При 1 &lt; ω &lt; 2 используем верхнюю релаксацию.",
        "<b>Условие сходимости</b><br/>Для SPD-матрицы гарантирована сходимость при 0 &lt; ω &lt; 2. Самого интервала без условий на A недостаточно.",
    ], 48, 238, 419, size=16, gap=21)
    deck.paragraphs([
        "<b>Выбор параметра</b><br/>Хороший ω ускоряет сходимость, значение около 2 может её замедлить и усилить колебания невязки.",
        "В квадрате используем теоретический оптимум. В комнате выбран ω = 1.8. Формула для простого квадрата не переносится автоматически на внутренние нагреватели.",
    ], 493, 238, 419, size=16, gap=21)
    deck.source("Теория: Netlib Templates, Choosing the Value of Omega [4]. В исходной квадратной реализации допускается 1 ≤ ω &lt; 2.")

    deck.start("Сходимость методов в квадрате", "Одинаковая сетка из 20 интервалов и относительный допуск 10⁻⁹")
    deck.image("figure_01.png", 38, 119, 557, 354)
    deck.table([
        ["<b>Метод</b>", "<b>Итерации</b>"],
        ["Якоби", "1385"], ["Зейдель", "694"], ["SOR", "80"],
    ], 617, 132, [170, 121], size=15, row_height=39)
    deck.text("SOR уменьшает число итераций примерно в 17 раз относительно Якоби при этих данных.",
              625, 318, 277, size=16)
    deck.text("Число итераций не равно времени исполнения: Python-циклы и операции NumPy имеют разную стоимость.",
              625, 404, 277, size=13, color=MUTED)
    deck.source("Источник: сохранённые результаты lab.ipynb, ячейка 25. Невязка приведена к её начальному значению.")

    deck.start("Оптимальный параметр SOR для квадрата")
    deck.equation("optimum", top=114, height=50)
    deck.image("figure_05.png", 38, 185, 635, 284)
    deck.paragraphs([
        "n = 20<br/><b>ω* = 1.72945382</b><br/>80 итераций.",
        "Этот же параметр дал лучший результат среди проверенных значений.",
        "Формулы относятся к квадрату без внутренних границ и потерь. Для постоянного уменьшения ошибки: Якоби и Зейдель O(n²) итераций, оптимальный SOR O(n).",
    ], 700, 184, 210, size=14.5, gap=16)
    deck.source("Источник: lab.ipynb, ячейка 31. Спектральная теория SOR для подходящих упорядочений: Netlib [4].")

    deck.start("Стационарное поле в квадрате", "Изолинии температуры для решения SOR")
    deck.image("figure_02.png", 52, 118, 475, 365)
    deck.paragraphs([
        "Снизу температура 400 °C, слева 100 °C. Поле отражает влияние четырёх заданных температур стенок.",
        "Фиксированные значения соседних сторон не согласованы в углах. Для отображения используем их среднее.",
        "Угловые узлы не входят во внутренний пятиузловой шаблон. Вблизи углов нельзя ожидать гладкости решения и равномерной оценки O(h²).",
    ], 565, 139, 340, size=17, gap=24)
    deck.source("Источник: lab.ipynb, ячейка 27. T = 100u. Угловая особенность относится к исходной постановке.")

    deck.start("Сечения температуры в квадрате")
    deck.image("figure_03.png", 40, 117, 880, 302)
    deck.text("Сечения проходят около четверти, середины и трёх четвертей стороны. В легендах указаны фактические координаты сеточных узлов. По графикам видно влияние разных граничных температур.",
              60, 433, 840, size=15, height=48)
    deck.source("Источник: lab.ipynb, ячейка 27. Решения Якоби, Зейделя и SOR приближают одно и то же поле.")

    deck.start("Ряд Фурье и ошибка сетки", "Независимое контрольное решение для квадратной области")
    deck.image("figure_04.png", 34, 121, 489, 290)
    deck.table([
        ["<b>n</b>", "<b>Ошибка SOR, °C</b>", "<b>p</b>"],
        ["10", "0.774705", "-"], ["20", "0.220029", "1.816"], ["40", "0.056968", "1.949"],
    ], 540, 127, [58, 207, 100], size=13.5, row_height=37)
    deck.text("Суммируем вклады четырёх сторон по 100 нечётным гармоникам. Ниже записан вклад левой стороны. Ошибку измеряем вдали от углов в [0.2L, 0.8L]².",
              548, 302, 351, size=14.5)
    deck.equation("fourier", x=58, top=421, width=827, height=57)
    deck.source("Источник: lab.ipynb, ячейка 29. p = log₂(Eₕ/Eₕ/₂) приближается к 2. Ряд также имеет ошибку усечения.")

    deck.start("Невязка и ошибка решения")
    deck.equation("residual", top=118, height=63)
    deck.paragraphs([
        "<b>В квадрате</b><br/>Контроль отношения норм невязок r и r₀. При нулевом начальном свободном поле r₀ соответствует правой части системы. Допуск 10⁻⁹.",
        "<b>В комнате</b><br/>Контроль η в °C. Для главной сетки η = 9.184·10⁻⁹ °C, исходная невязка 9.432·10⁻⁶ Вт/м².",
    ], 48, 217, 419, size=16, gap=22)
    deck.equation("bound", x=489, top=219, width=420, height=60)
    deck.paragraphs([
        "Здесь e есть точное дискретное решение минус текущее приближение. Диагональный запас H даёт оценку ошибки <b>разностной системы</b> при H &gt; 0.",
        "Для комнаты оценка порядка 3.2·10⁻⁶ °C. Она не включает ошибку сетки, геометрии и физической модели. При H = 0 эта оценка неприменима.",
    ], 493, 303, 419, size=15.5, gap=19)
    deck.source("Источник чисел: lab.ipynb, ячейка 33. Оценка ошибки выведена для данной M-матрицы с H &gt; 0.")

    deck.start("Источники погрешности и нештатные случаи")
    deck.table([
        ["<b>Источник</b>", "<b>Как проявляется</b>", "<b>Как проверяем</b>"],
        ["Итерационная ошибка", "Решатель ещё не достиг AT = b", "Невязка и независимая СЛАУ"],
        ["Ошибка сетки", "Центральная схема O(hₓ² + hᵧ²) для гладкого поля", "Сгущение и ряд Фурье"],
        ["Геометрия", "Край полосы смещается при смене сетки", "Поля на двух сетках"],
        ["Округление и ряд", "Предел точности float64, усечение гармоник", "Разумный допуск и контроль области"],
        ["Физическая модель", "Нет движения воздуха и предела мощности", "Уточнение исходной постановки"],
    ], 48, 126, [164, 402, 298], size=14, row_height=48)
    deck.text("Неверные размеры, коэффициенты, ω, неразрешённые объекты и конфликт температур вызывают явную ошибку. Превышение лимита итераций также завершает расчёт с ошибкой.",
              56, 437, 848, size=14.5, height=45)
    deck.source("Контроль ошибок и проверки входных данных реализованы в lab.ipynb. Порядок схемы требует гладкости решения.")

    deck.start("Температурное поле с надписью «РТ»", "Комната 10 × 6 м, сетка 161 × 97 узлов, обогреватели 65 °C")
    deck.image("figure_07.png", 43, 115, 628, 368)
    deck.paragraphs([
        "<b>197 итераций SOR</b><br/>ω = 1.8, η &lt; 10⁻⁸ °C.",
        "Диапазон 5…65 °C. На итоговое поле не наложены буквы или маска надписи.",
        "Размещение полос задано конструктивно. Результат показывает существование подходящей схемы, но не её оптимальность.",
    ], 704, 136, 205, size=15.5, gap=23)
    deck.source("Источник: lab.ipynb, ячейки 33-34. Поле показывает температуру в принятой двумерной модели.")

    deck.start("Роль распределённых потерь тепла")
    deck.image("figure_08.png", 36, 124, 888, 253)
    deck.equation("length", x=56, top=395, width=280, height=52)
    deck.text("Без потерь замкнутый просвет «Р» почти достигает температуры полос. H &gt; 0 позволяет ему отдавать тепло через пол и потолок. Все три карты используют одну шкалу.",
              365, 397, 535, size=16, height=77)
    deck.source("Источник: lab.ipynb, ячейка 36. При H = 0 справа и в центре была бы одна постановка.")

    deck.start("Сходимость и температурные сечения комнаты")
    deck.image("figure_09.png", 36, 118, 888, 313)
    deck.text("Потери тепла ускоряют затухание пространственных возмущений. Сечения пересекают полосы и показывают, как быстро температура убывает между ними. Пики 65 °C соответствуют заданным температурам обогревателей.",
              56, 442, 848, size=14.5, height=44)
    deck.source("Источник: lab.ipynb, ячейка 36. Горизонтальная шкала слева показывает итерации SOR.")

    deck.start("Сравнение методов в комнате", "Одинаковая грубая сетка 81 × 49 узлов и абсолютный допуск η ≤ 10⁻⁸ °C")
    deck.image("figure_10.png", 34, 120, 554, 346)
    deck.table([
        ["<b>Метод</b>", "<b>Итерации</b>"],
        ["Якоби", "1033"], ["Шахматный Зейдель", "537"], ["SOR, ω = 1.8", "98"],
    ], 606, 129, [188, 112], size=13.5, row_height=43)
    deck.text("Все методы сходятся к одной разностной температуре. Для этой сетки SOR требует примерно в 10.5 раза меньше итераций, чем Якоби.",
              614, 332, 286, size=16)
    deck.source("Источник: lab.ipynb, ячейка 38. Главная иллюстрация «РТ» рассчитана на более мелкой сетке.")

    deck.start("Сгущение сетки в комнате")
    deck.image("figure_11.png", 35, 116, 890, 306)
    deck.text("Общие свободные узлы: среднеквадратическое различие <b>0.6350 °C</b>, максимальное <b>5.2841 °C</b>. Это различие двух дискретизаций, а не доказанная ошибка точного решения. Края полос меняют привязку к узлам.",
              56, 435, 848, size=15.5, height=50)
    deck.source("Источник: lab.ipynb, ячейка 38. Сравнение 160 × 96 и 320 × 192 интервалов. Читаемость сохраняется.")

    deck.start("Независимые проверки реализации")
    deck.table([
        ["<b>Проверка</b>", "<b>Что подтверждает</b>"],
        ["Плотная СЛАУ на малой сетке", "Совпадение трёх методов с np.linalg.solve"],
        ["SOR с ω = 1", "Совпадение с соответствующим методом Зейделя"],
        ["Постоянная температура", "Сохранение точного равномерного решения"],
        ["Стены, окна, обогреватели", "Фиксированные значения не обновляются"],
        ["Принцип максимума", "Поле не выходит за допустимые границы"],
        ["Связь двух постановок", "При H = 0 без приборов квадратные модели совпадают"],
    ], 48, 121, [345, 519], size=15, row_height=43)
    deck.text("np.linalg.solve используется как контроль на малой системе. Ряд Фурье дополнительно проверяет ошибку сетки в исходном квадрате.",
              56, 441, 848, size=15, height=42)
    deck.source("Источник: lab.ipynb, ячейки 41, 43, 45. Все встроенные проверки завершились успешно.")

    deck.start("Модель установления температуры во времени")
    deck.equation("transient", top=114, height=54)
    deck.equation("ftcs", top=184, height=59)
    deck.equation("cfl", top=262, height=60)
    deck.paragraphs([
        "Явный Эйлер по времени и центральные разности по пространству. Достаточное условие выше сохраняет неотрицательные веса и устойчивость. Порядок для гладкого решения: O(Δt + Δx² + Δy²).",
        f"C = 1000 Дж/(м²·К) выбрано для иллюстрации. Δt = {transient['dt']:.6f} с, левая часть условия = 0.9. Изменение C меняет время процесса, но не конечное поле.",
    ], 48, 347, 864, size=15.5, gap=15)
    deck.source("Базовая явная схема: Oxford, Ian Reid, Exercise 6 [5]. Условие с H выведено из весов нашей схемы.")

    deck.start("Анимация установления теплового поля", "В момент t = 0 включаем полосы 65 °C, свободные узлы имеют температуру 18 °C")
    for name, x in (("transient_start", 35), ("transient_middle", 337), ("transient_end", 639)):
        deck.image(f"{name}.png", x, 132, 286, 253)
    deck.text(f"GIF содержит {transient['frames']} кадр. Время модели до последнего кадра {transient['time_end']:.1f} с (около {transient['time_end'] / 60:.1f} мин). Воспроизведение ускорено, время указано на каждом кадре.",
              56, 411, 848, size=16, height=52)
    deck.source("Файл анимации: output/gif/thermal_letters.gif. PDF содержит статичные кадры. Временная шкала условна из-за выбранного C.")

    deck.start("Контроль нестационарного расчёта")
    deck.image("transient_convergence.png", 40, 123, 546, 336)
    deck.paragraphs([
        f"К последнему кадру отличие от стационарного SOR-поля &lt; <b>{0.01:.2f} °C</b> по максимуму узлов.",
        f"При уменьшении шага времени вдвое различие на t ≈ 300 с равно <b>{transient['temporal_refinement_difference']:.4f} °C</b>.",
        "Сохраняются фиксированные узлы и температурные пределы. Проверены постоянное поле и неподвижность стационарного решения.",
    ], 618, 133, 287, size=16, gap=22)
    deck.source("Новые расчёты: materials/prepare_artifacts.py. Разность с установившимся полем характеризует остаточный переходный процесс.")

    deck.start("Источники и воспроизведение")
    references = [
        ('[1] Netlib. The Jacobi Method', 'https://netlib.org/linalg/html_templates/node12.html'),
        ('[2] Netlib. Convergence of the Jacobi method', 'https://netlib.org/linalg/html_templates/node13.html'),
        ('[3] Netlib. The Gauss-Seidel Method', 'https://netlib.org/linalg/html_templates/node14.html'),
        ('[4] Netlib. Choosing the Value of Omega', 'https://netlib.org/linalg/html_templates/node16.html'),
        ('[5] Oxford. Ian Reid. Exercise 6: PDEs, 1999', 'https://www.robots.ox.ac.uk/~ian/Teaching/Computation/lab6.pdf'),
    ]
    top = 120
    for label, url in references:
        deck.text(label, 48, top, 864, size=14.5, height=24, bold=True)
        deck.text(f'<link href="{url}" color="#236a96">{url}</link>', 48, top + 23,
                   864, size=11.5, height=20)
        top += 57
    deck.text("Графики и исходные числа: thermal_letters/lab.ipynb. Слайды включают все 11 сохранённых графиков. Новая динамика использует ту же геометрию и те же граничные температуры.",
              48, 415, 864, size=14, height=42)
    deck.text("Сборка: materials/prepare_artifacts.py, затем materials/build_presentation.py. Инструкции и зависимости находятся в README работы.",
              48, 464, 864, size=12, height=34, color=MUTED)
    deck.save()
    print(f"Saved {deck.page} slides: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "tmp/pdfs/thermal_letters/assets")
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/thermal_letters.pdf")
    parser.add_argument("--font-directory", type=Path, default=Path("C:/Windows/Fonts"))
    args = parser.parse_args()
    build(args.output, args.assets, args.font_directory)


if __name__ == "__main__":
    main()
