"""Run: python generate_aliases.py --limit 1 --dry-run"""
import argparse
import json
import sys
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select

from config import ROOT
from database import Base, SessionLocal, engine
from models.data_model import LDAPUser, UserAlias
from services.gemini_alias_service import clean_aliases, generate_aliases, save_aliases
from services.avalai_client import AvalAIClient, completion_url


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    llm_key: SecretStr
    llm_model: str
    llm_url: str


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate aliases through AvalAI using LLM_URL, LLM_KEY and LLM_MODEL.')
    parser.add_argument('--uid', type=UUID, help='Process only this user')
    parser.add_argument('--limit', type=positive, help='Maximum users (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Call AvalAI and print aliases without saving them')
    parser.add_argument('--enabled-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        settings = LLMSettings()
        if not settings.llm_key.get_secret_value().strip() or not settings.llm_model.strip():
            raise ValueError('Empty configuration')
        completion_url(settings.llm_url)
    except Exception:
        print('Set valid LLM_URL, non-empty LLM_KEY and LLM_MODEL in .env.', file=sys.stderr)
        return 2
    Base.metadata.create_all(engine)
    statement = select(LDAPUser.uid).order_by(LDAPUser.uid)
    if args.uid:
        statement = statement.where(LDAPUser.uid == str(args.uid))
    if args.enabled_only:
        statement = statement.where(LDAPUser.enabled.is_(True))
    if args.limit:
        statement = statement.limit(args.limit)
    with SessionLocal() as session:
        ids = list(session.scalars(statement))
    if not ids:
        print('No matching users. Sync LDAP first or check --uid.')
        return 1 if args.uid else 0
    failures = 0
    total = 0
    with AvalAIClient(api_key=settings.llm_key.get_secret_value(), url=settings.llm_url) as client:
        for index, uid in enumerate(ids, 1):
            with SessionLocal() as session:
                try:
                    user = session.get(LDAPUser, uid)
                    if user is None:
                        continue
                    if not any([user.first_name, user.last_name, user.display_name]):
                        print(f'[{index}/{len(ids)}] {uid}: skipped (no names)')
                        continue
                    existing = list(session.scalars(select(UserAlias.name).where(UserAlias.user_uid == uid)))
                    # Detach the snapshot and end the read transaction during the network request.
                    session.expunge(user)
                    session.rollback()
                    generated = generate_aliases(client, settings.llm_model, user, existing)
                    aliases = clean_aliases(generated, existing)
                    if args.dry_run:
                        print(json.dumps(dict(uid=uid, aliases=[name for name, _ in aliases]), ensure_ascii=False))
                    else:
                        count = save_aliases(session, uid, aliases)
                        session.commit()
                        total += count
                        print(f'[{index}/{len(ids)}] {uid}: added {count}')
                except KeyboardInterrupt:
                    session.rollback()
                    print('Interrupted. Previously committed users are preserved.', file=sys.stderr)
                    return 130
                except Exception as error:
                    session.rollback()
                    failures += 1
                    # SDK error text can include request data; log only class and status code.
                    code = getattr(error, 'code', None)
                    print(f'{uid}: failed ({type(error).__name__}, status={code})', file=sys.stderr)
                    if code in (400, 401, 403, 404):
                        print('Stopped: check AvalAI URL, key, model, JSON-mode support and API access.', file=sys.stderr)
                        break
    print(f'Finished: added={total}, failures={failures}, dry_run={args.dry_run}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
