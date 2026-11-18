"""Name normalization and conservative, explainable similarity scoring."""
import unicodedata

from rapidfuzz.distance import DamerauLevenshtein

TRANSLATION = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ـ': ''})


def normalize_name(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).translate(TRANSLATION).casefold()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.category(c).startswith('M'))
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text).split())


def score_name(query: str, candidate: str) -> tuple[float, str]:
    """Inputs are normalized; scores are ranking values, not probabilities."""
    if not query or not candidate:
        return 0.0, 'none'
    if query == candidate:
        return 100.0, 'exact'
    q_tokens, c_tokens = query.split(), candidate.split()
    if sorted(q_tokens) == sorted(c_tokens):
        return 99.0, 'reordered'
    # Short queries require exact tokens or prefixes, never typo matching.
    remaining = c_tokens.copy()
    for token in q_tokens:
        match = next((c for c in remaining if c.startswith(token)), None)
        if match is None:
            break
        remaining.remove(match)
    else:
        if len(query.replace(' ', '')) >= 2:
            return 95.0, 'prefix'
    if len(query.replace(' ', '')) < 4:
        return 0.0, 'none'
    similarity = max(
        DamerauLevenshtein.normalized_similarity(query, candidate),
        DamerauLevenshtein.normalized_similarity(' '.join(sorted(q_tokens)), ' '.join(sorted(c_tokens))),
    )
    return round(similarity * 94, 2), 'fuzzy'
