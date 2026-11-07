SITE_NAME = "Aquele que Observa"

CATEGORIES = [
    {"key": "personagem", "label": "Personagens", "single": "Personagem", "icon": "ri:hood"},
    {"key": "local", "label": "Locais", "single": "Local", "icon": "ri:castle"},
    {"key": "faccao", "label": "Facções", "single": "Facção", "icon": "ri:shield"},
    {"key": "criatura", "label": "Criaturas", "single": "Criatura", "icon": "ri:beast"},
    {"key": "item", "label": "Itens", "single": "Item", "icon": "ri:gem"},
    {"key": "evento", "label": "Eventos", "single": "Evento", "icon": "ri:fire"},
    {"key": "livro", "label": "Livros e registros", "single": "Livro / registro", "icon": "ri:book"},
    {"key": "nota", "label": "Notas", "single": "Nota", "icon": "ri:quill"},
]
CATEGORY_MAP = {c["key"]: c for c in CATEGORIES}

# Paleta do site
THEMES = ("dark", "light")
ACCENTS = {
    "yellow": "Amarelo",
    "red": "Vermelho",
    "blue": "Azul",
    "pink": "Rosa",
    "purple": "Roxo",
    "green": "Verde",
}
ACCENT_SWATCH = {
    "yellow": "#f59e0b", "red": "#ef4444", "blue": "#3b82f6",
    "pink": "#ec4899", "purple": "#8b5cf6", "green": "#10b981",
}

# Cores dos cards nos mapas mentais: (fundo do card, bolinha do seletor)
CARD_COLORS = {
    "yellow": ("bg-amber-100", "bg-amber-300"),
    "green": ("bg-emerald-100", "bg-emerald-300"),
    "blue": ("bg-sky-100", "bg-sky-300"),
    "pink": ("bg-rose-100", "bg-rose-300"),
    "purple": ("bg-violet-100", "bg-violet-300"),
    "white": ("bg-white", "bg-stone-200"),
}

PIN_COLORS = ["#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#8b5cf6", "#10b981", "#f5f5f4", "#1c1917"]

# Relações entre páginas. (frase de A para B, frase de B para A)
RELATION_KINDS = {
    "parent": ("é pai/mãe de", "é filho(a) de"),
    "spouse": ("é cônjuge de", "é cônjuge de"),
    "sibling": ("é irmão(ã) de", "é irmão(ã) de"),
    "twin": ("é gêmeo(a) de", "é gêmeo(a) de"),
    "half_sibling": ("é meio-irmão(ã) de", "é meio-irmão(ã) de"),
    "ex_spouse": ("é ex-cônjuge de", "é ex-cônjuge de"),
    "betrothed": ("é noivo(a) de", "é noivo(a) de"),
    "adopt": ("adotou", "foi adotado(a) por"),
    "guardian": ("é tutor(a) de", "está sob tutela de"),
    "ally": ("é aliado(a) de", "é aliado(a) de"),
    "enemy": ("é inimigo(a) de", "é inimigo(a) de"),
    "member": ("é membro de", "tem como membro"),
    "location": ("fica / vive em", "abriga"),
    "owns": ("possui", "pertence a"),
    "other": ("", ""),
}


def relation_options():
    """Opções do <select>: 'kind>' = esta página é A; 'kind<' = esta página é B."""
    opts = []
    for kind, (fwd, back) in RELATION_KINDS.items():
        if kind == "other":
            continue
        opts.append((f"{kind}>", fwd))
        if back != fwd:
            opts.append((f"{kind}<", back))
    opts.append(("other>", "outra relação (escreva abaixo)…"))
    return opts


# Upload: extensão -> mimetype. SVG/HTML ficam de fora de propósito (risco de XSS).
IMAGE_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp", "avif": "image/avif",
}
DOC_TYPES = {
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "doc": "application/msword",
    "zip": "application/zip",
}
AUDIO_TYPES = {
    "mp3": "audio/mpeg", "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
    "wav": "audio/wav", "m4a": "audio/mp4", "aac": "audio/aac", "flac": "audio/flac",
}
VIDEO_TYPES = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}
UPLOAD_TYPES = {**IMAGE_TYPES, **DOC_TYPES, **AUDIO_TYPES, **VIDEO_TYPES}
