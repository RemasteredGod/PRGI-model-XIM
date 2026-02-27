import jellyfish
from backend.database import PHONETIC_CACHE, SOUNDEX_INDEX, NYSIIS_INDEX

def get_phonetic_codes(title: str):
    words = title.upper().split()
    soundex_codes = {jellyfish.soundex(word) for word in words if word}
    nysiis_codes = {jellyfish.nysiis(word) for word in words if word}
    return soundex_codes, nysiis_codes

def check_phonetic(title: str, existing_titles: list[str]) -> list[dict]:
    t_soundex, t_nysiis = get_phonetic_codes(title)

    if not t_soundex and not t_nysiis:
        return []

    # Use reverse index: only score titles that share ≥1 phonetic code.
    # Reduces O(70k) iterations to O(candidates) — typically 100–2,000 titles.
    candidates: set = set()
    for code in t_soundex:
        candidates.update(SOUNDEX_INDEX.get(code, set()))
    for code in t_nysiis:
        candidates.update(NYSIIS_INDEX.get(code, set()))

    # Fallback to full scan on first call before index is built
    if not candidates and existing_titles:
        candidates = set(existing_titles)

    results = []
    for existing in candidates:
        pair = PHONETIC_CACHE.get(existing)
        if pair:
            e_soundex, e_nysiis = pair
        else:
            e_soundex, e_nysiis = get_phonetic_codes(existing)

        # Soundex overlap
        s_overlap = t_soundex & e_soundex
        s_score = (len(s_overlap) / max(len(t_soundex), len(e_soundex))) * 100 if max(len(t_soundex), len(e_soundex)) > 0 else 0

        # NYSIIS overlap
        n_overlap = t_nysiis & e_nysiis
        n_score = (len(n_overlap) / max(len(t_nysiis), len(e_nysiis))) * 100 if max(len(t_nysiis), len(e_nysiis)) > 0 else 0

        final_score = max(s_score, n_score)

        if final_score > 30:
            results.append({
                "existing_title": existing,
                "match_percentage": round(final_score, 2),
                "match_type": "phonetic"
            })

    return results
