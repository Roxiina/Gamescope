"""Outils communs : session HTTP avec relances, journalisation, fichiers JSONL."""
import hashlib
import json
import logging
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from extraction import config


def setup_logging(name: str = "extraction") -> logging.Logger:
    """Journalise à la fois dans la console et dans logs/<name>.log."""
    config.LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(config.LOG_DIR / f"{name}.log", encoding="utf-8"),
        ],
    )
    return logging.getLogger(name)


def build_session() -> requests.Session:
    """Session HTTP qui relance automatiquement sur erreurs réseau et 429/5xx.

    Relances courtes (1 s, 2 s, 4 s) pour les erreurs passagères ; le bridage
    prolongé est géré par `throttled_get` avec de longues pauses.
    """
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = config.USER_AGENT
    return session


class RateLimiter:
    """Garantit un délai minimal entre deux appels à une même source."""

    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last = time.monotonic()


COOLDOWNS = (60, 120, 240)  # secondes de pause successives quand la source bride


def throttled_get(session: requests.Session, limiter: RateLimiter, url: str,
                  log: logging.Logger, **kwargs) -> requests.Response:
    """GET qui survit au bridage de Steam.

    Steam signale un dépassement de débit par des 502 (et non des 429) :
    on fait une pause de plus en plus longue puis on réessaie la même
    requête, au lieu d'abandonner le jeu.
    """
    for attempt, cooldown in enumerate((*COOLDOWNS, None), 1):
        limiter.wait()
        try:
            resp = session.get(url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if cooldown is None:
                raise
            log.warning("Bridage ou erreur réseau (tentative %d) : pause de %d s - %s",
                        attempt, cooldown, type(exc).__name__)
            time.sleep(cooldown)
    raise AssertionError("inaccessible")


def pseudonymize(identifier: str) -> str:
    """Hash SHA-256 salé : l'identifiant réel n'est jamais stocké (RGPD)."""
    if not config.PSEUDO_SALT:
        raise RuntimeError("PSEUDO_SALT absent du .env : pseudonymisation impossible")
    return hashlib.sha256((config.PSEUDO_SALT + str(identifier)).encode()).hexdigest()


def read_done_ids(path: Path, key: str = "appid") -> set[int]:
    """Identifiants déjà extraits, pour reprendre une collecte interrompue."""
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                done.add(int(json.loads(line)[key]))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue  # ligne tronquée par un arrêt brutal : ignorée
    return done


def append_jsonl(path: Path, record: dict) -> None:
    """Ajoute un enregistrement immédiatement : aucune perte si le script s'arrête."""
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
