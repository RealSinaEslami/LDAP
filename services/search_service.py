from sqlalchemy import select
from sqlalchemy.orm import Session

from models.data_model import LDAPUser, UserAlias
from services.name_matching import normalize_name, score_name


def search_users(session: Session, query: str, limit=10, min_score=70, enabled_only=False):
    normalized = normalize_name(query)
    if not normalized:
        return []
    statement = select(LDAPUser)
    if enabled_only:
        statement = statement.where(LDAPUser.enabled.is_(True))
    aliases = {}
    for alias in session.scalars(select(UserAlias)):
        aliases.setdefault(alias.user_uid, []).append(alias.name)
    hits = []
    for user in session.scalars(statement):
        candidates = [
            ('display_name', user.display_name), ('username', user.username),
            ('full_name', ' '.join(n for n in [user.first_name, user.last_name] if n)),
        ]
        candidates.extend(('alias', name) for name in aliases.get(user.uid, []))
        best = None
        for field, name in candidates:
            if not name:
                continue
            score, kind = score_name(normalized, normalize_name(name))
            if score > 0 and score >= min_score and (best is None or score > best['score']):
                best = dict(user=user, score=score, matched_name=name,
                            matched_field=field, match_type=kind)
        if best:
            hits.append(best)
    hits.sort(key=lambda hit: (-hit['score'], hit['user'].uid))
    return hits[:limit]
