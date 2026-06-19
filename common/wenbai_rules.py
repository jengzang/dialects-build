import re

WEN_BAI_LITERARY_MARK = '2'
WEN_BAI_COLLOQUIAL_MARK = '3'
WEN_BAI_MARKS = {
    '=': WEN_BAI_LITERARY_MARK,
    '-': WEN_BAI_COLLOQUIAL_MARK,
}

WEN_BAI_NOTE_PATTERNS = [
    (re.compile(r'\[文\]|\(文\)|（文）'), WEN_BAI_LITERARY_MARK),
    (re.compile(r'\[白\]|\(白\)|（白）'), WEN_BAI_COLLOQUIAL_MARK),
    (re.compile(r'^\s*(?:文讀|文读|文)(?=$|[：:，,;；\s])'), WEN_BAI_LITERARY_MARK),
    (re.compile(r'^\s*(?:白讀|白读|白)(?=$|[：:，,;；\s])'), WEN_BAI_COLLOQUIAL_MARK),
    (re.compile(r'^\s*(?:讀書音|读书音)(?=$|[：:，,;；\s])'), WEN_BAI_LITERARY_MARK),
]

WEN_BAI_NOTE_INLINE_PATTERN = re.compile(r'\s*(?:\[文\]|\[白\]|\(文\)|\(白\)|（文）|（白）)\s*')
WEN_BAI_NOTE_PREFIX_PATTERN = re.compile(r'^\s*(?:文讀|文读|白讀|白读|讀書音|读书音|文(?=$|[：:，,;；\s])|白(?=$|[：:，,;；\s]))\s*(?:[：:，,;；]\s*)?')
WEN_BAI_NOTE_EDGE_PUNCT_PATTERN = re.compile(r'^[\s：:，,;；]+|[\s：:，,;；]+$')


def split_wenbai_marker(value):
    text = '' if value is None else str(value).strip()
    if not text:
        return '', ''

    marker = WEN_BAI_MARKS.get(text[-1])
    if marker:
        return text[:-1].strip(), marker
    return text, ''


def detect_wenbai_from_note(note):
    text = '' if note is None else str(note).strip()
    if not text:
        return ''

    for pattern, marker in WEN_BAI_NOTE_PATTERNS:
        if pattern.search(text):
            return marker
    return ''


def clean_wenbai_note(note):
    text = '' if note is None else str(note).strip()
    if not text:
        return ''

    text = WEN_BAI_NOTE_PREFIX_PATTERN.sub('', text)
    text = WEN_BAI_NOTE_INLINE_PATTERN.sub('', text)
    text = WEN_BAI_NOTE_EDGE_PUNCT_PATTERN.sub('', text)
    return text.strip()


def merge_wenbai_markers(primary_marker, note_marker):
    primary = '' if primary_marker is None else str(primary_marker).strip()
    if primary:
        return primary
    return '' if note_marker is None else str(note_marker).strip()
