import os
import re
import sys
import signal
import logging
import argparse
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import (
    COMPETITIONS_DETAILS,
    COMPETITIONS_BY_CODE,
    COMPETITIONS,
    CACHE_DIR,
    CHECKPOINT_DIR,
    CACHE_NEVER_EXPIRES,
    MIN_MATCHES_FOR_TRAINING,
    MANIFEST_FILE,
    CONFIG_FINGERPRINT,
    ARTIFACT_SCHEMA_VERSION,
    EXPECTED_FEATURE_COUNT_REFERENCE,
    EXPECTED_CLASS_COUNT,
    HISTORICAL_SEASONS_LOOKBACK,
    BZZOIRO_ENRICH_XG,
    BZZOIRO_WORKERS_PER_KEY,
    BZZOIRO_MAX_WORKERS,
    TOKEN_COUNT,
    now_local,
    stage_print,
)
from predict import load_or_build_data_and_models, predict_for_date

logger = logging.getLogger("goangel.main")

RESET: str = "\033[0m"
BOLD: str = "\033[1m"
DIM: str = "\033[2m"
ITALIC: str = "\033[3m"

RED: str = "\033[1;31m"
GREEN: str = "\033[1;32m"
YELLOW: str = "\033[1;33m"
BLUE: str = "\033[1;34m"
MAGENTA: str = "\033[1;35m"
CYAN: str = "\033[1;36m"
WHITE: str = "\033[1;37m"
GREY: str = "\033[0;90m"
ORANGE: str = "\033[38;5;208m"
LIME: str = "\033[38;5;154m"
PINK: str = "\033[38;5;213m"
VIOLET: str = "\033[38;5;135m"
SKY: str = "\033[38;5;117m"
GOLD: str = "\033[38;5;220m"

_BANNER_LOGO: List[str] = [
    r"   ██████╗  ██████╗  █████╗ ███╗   ██╗ ██████╗ ███████╗██╗     ",
    r"  ██╔════╝ ██╔═══██╗██╔══██╗████╗  ██║██╔════╝ ██╔════╝██║     ",
    r"  ██║  ███╗██║   ██║███████║██╔██╗ ██║██║  ███╗█████╗  ██║     ",
    r"  ██║   ██║██║   ██║██╔══██║██║╚██╗██║██║   ██║██╔══╝  ██║     ",
    r"  ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║╚██████╔╝███████╗███████╗",
    r"   ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚══════╝",
]

_BANNER_COLORS: List[str] = [RED, ORANGE, GOLD, LIME, SKY, VIOLET]

_TITLE: str = "GOANGEL SYSTEM"
_SUBTITLE: str = "★MOTEUR DE PRÉDICTIONS FOOTBALLISTIQUES MULTI-MODÈLES ★"
_VERSION: str = f"v23 — ARCTIQUE — {EXPECTED_FEATURE_COUNT_REFERENCE} FEATURES"
_TAGLINE: str = "★ ANALYSE · STATISTIQUES · ENSEMBLE LEARNING · CALIBRATION★"

_SHUTDOWN_FLAG: Dict[str, bool] = {"requested": False}

_MIN_YEAR: int = 1990
_MAX_YEAR: int = 2100

_TUPLE_LEN_EXPECTED: int = 5

_BANNER_WIDTH_MIN: int = 68
_BANNER_WIDTH_MAX: int = 100
_SEPARATOR_LEN: int = 70

_DATE_FORMAT_ISO: str = "%Y-%m-%d"

_QUIT_COMMANDS: frozenset = frozenset({"quit", "exit", "q"})
_HELP_COMMANDS: frozenset = frozenset({"help", "h", "?"})
_COMPETITIONS_COMMANDS: frozenset = frozenset({"competitions", "comps", "c"})
_CLEAR_COMMANDS: frozenset = frozenset({"clear", "cls"})
_REFRESH_COMMANDS: frozenset = frozenset({"refresh", "reload", "r"})
_STATUS_COMMANDS: frozenset = frozenset({"status", "info"})
_TODAY_COMMANDS: frozenset = frozenset({"today", "aujourd'hui", "aujourdhui"})
_YESTERDAY_COMMANDS: frozenset = frozenset({"yesterday", "hier"})
_TOMORROW_COMMANDS: frozenset = frozenset({"tomorrow", "demain"})

_FULL_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*[/\-\.]\s*(\d{1,2})\s*[/\-\.]\s*(\d{4})\s*$")
_DAY_MONTH_RE = re.compile(r"^\s*(\d{1,2})\s*[/\-\.]\s*(\d{1,2})\s*$")
_DAY_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s*$")


def _visible_len(text: str) -> int:
    result = 0
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\033":
            j = text.find("m", i)
            if j == -1:
                break
            i = j + 1
            continue
        result += 1
        i += 1
    return result


def _center_colored(text: str, width: int) -> str:
    visible = _visible_len(text)
    if visible >= width:
        return text
    left = (width - visible) // 2
    right = width - visible - left
    return (" " * left) + text + (" " * right)


def _safe_terminal_width() -> int:
    try:
        w = os.get_terminal_size().columns
        if w < _BANNER_WIDTH_MIN:
            return _BANNER_WIDTH_MIN
        if w > _BANNER_WIDTH_MAX:
            return _BANNER_WIDTH_MAX
        return int(w)
    except (OSError, ValueError, AttributeError):
        return _BANNER_WIDTH_MIN + 8


def print_banner() -> None:
    try:
        banner_width = _safe_terminal_width()
        term_width = _safe_terminal_width()
        left_pad = max(0, (term_width - banner_width) // 2)

        print()
        print(" " * left_pad + f"{GREY}╔" + "═" * (banner_width - 2) + f"╗{RESET}")

        for i, line in enumerate(_BANNER_LOGO):
            color = _BANNER_COLORS[i % len(_BANNER_COLORS)]
            inner = _center_colored(f"{color}{BOLD}{line}{RESET}", banner_width - 4)
            print(" " * left_pad + f"{GREY}║{RESET} " + inner + f" {GREY}║{RESET}")

        print(" " * left_pad + f"{GREY}╠" + "═" * (banner_width - 2) + f"╣{RESET}")

        title_line = (
            f"{GOLD}{BOLD}★★ {_TITLE} ★★{RESET}  "
            f"{DIM}{GREY}({_VERSION}){RESET}"
        )
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(title_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        subtitle_line = f"{CYAN}{_SUBTITLE}{RESET}"
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(subtitle_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        tagline_line = f"{DIM}{ITALIC}{LIME}{_TAGLINE}{RESET}"
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(tagline_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        print(" " * left_pad + f"{GREY}╠" + "═" * (banner_width - 2) + f"╣{RESET}")

        cache_label = "PERMANENT" if CACHE_NEVER_EXPIRES else "avec expiration"
        cache_color = GREEN if CACHE_NEVER_EXPIRES else YELLOW
        cache_line = (
            f"{SKY}💾 Cache {cache_color}{BOLD}{cache_label}{RESET}"
            f"{SKY} : {CACHE_DIR}{RESET}"
        )
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(cache_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        comp_line = (
            f"{GOLD}🏆 🏆LIGUES ARCTIQUE 🏆🏆 : {BOLD}{len(COMPETITIONS_DETAILS)}{RESET}"
        )
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(comp_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        try:
            now_str = now_local().strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        time_line = f"{GOLD}★ {SKY}🕒 {now_str}{GOLD} ★{RESET}"
        print(
            " " * left_pad
            + f"{GREY}║{RESET} "
            + _center_colored(time_line, banner_width - 4)
            + f" {GREY}║{RESET}"
        )

        print(" " * left_pad + f"{GREY}╚" + "═" * (banner_width - 2) + f"╝{RESET}")
        print()
    except Exception:
        print("GOANGEL SYSTEM")
        print()


def print_section(title: str, color: str = CYAN) -> None:
    print()
    padding = max(0, _SEPARATOR_LEN - len(title))
    print(f"{color}── {title} " + "─" * padding + f"{RESET}")


def clear_screen() -> None:
    try:
        os.system("clear" if os.name == "posix" else "cls")
    except Exception:
        pass
    print_banner()


def _now_local() -> datetime:
    return now_local()


def _iso_from_datetime(dt: datetime) -> str:
    return dt.strftime(_DATE_FORMAT_ISO)


def _try_full_date(ui: str) -> Optional[datetime]:
    m = _FULL_DATE_RE.match(ui)
    if not m:
        return None
    day = int(m.group(1))
    month = int(m.group(2))
    year = int(m.group(3))
    if year < _MIN_YEAR or year > _MAX_YEAR:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _try_day_month(ui: str, now: datetime) -> Optional[datetime]:
    m = _DAY_MONTH_RE.match(ui)
    if not m:
        return None
    day = int(m.group(1))
    month = int(m.group(2))
    year = now.year
    if year < _MIN_YEAR or year > _MAX_YEAR:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _try_day_only(ui: str, now: datetime) -> Optional[datetime]:
    m = _DAY_ONLY_RE.match(ui)
    if not m:
        return None
    day = int(m.group(1))
    month = now.month
    year = now.year
    if year < _MIN_YEAR or year > _MAX_YEAR:
        return None
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_date_smart(user_input: str) -> Tuple[Optional[str], str, str]:
    if not isinstance(user_input, str):
        return None, "", "entrée invalide"
    ui = user_input.strip()
    if not ui:
        return None, "", "entrée vide"

    now = _now_local()
    today = now.date()

    if ui in _TODAY_COMMANDS:
        dt_ = datetime(today.year, today.month, today.day)
        return _iso_from_datetime(dt_), "today", "commande today"
    if ui in _YESTERDAY_COMMANDS:
        y = today - timedelta(days=1)
        dt_ = datetime(y.year, y.month, y.day)
        return _iso_from_datetime(dt_), "yesterday", "commande yesterday"
    if ui in _TOMORROW_COMMANDS:
        t = today + timedelta(days=1)
        dt_ = datetime(t.year, t.month, t.day)
        return _iso_from_datetime(dt_), "tomorrow", "commande tomorrow"

    full = _try_full_date(ui)
    if full is not None:
        return _iso_from_datetime(full), "full", f"date explicite {full.strftime('%d/%m/%Y')}"

    dm = _try_day_month(ui, now)
    if dm is not None:
        return (
            _iso_from_datetime(dm),
            "day_month",
            f"jour+mois explicite, année={now.year}",
        )

    do = _try_day_only(ui, now)
    if do is not None:
        return (
            _iso_from_datetime(do),
            "auto",
            f"jour seul → {do.strftime('%d/%m/%Y')} (mois+année détectés depuis le système)",
        )

    return None, "", "format non reconnu"


def _pretty_iso(date_iso: str) -> str:
    try:
        dt_ = datetime.strptime(date_iso, _DATE_FORMAT_ISO)
        return dt_.strftime("%d/%m/%Y")
    except Exception:
        return date_iso


def display_competitions() -> None:
    print_section(f"Ligues Arctique suivies ({len(COMPETITIONS_DETAILS)})", CYAN)
    for comp in COMPETITIONS_DETAILS:
        group_color = {
            "EUROPE_TOP5": LIME,
            "EUROPE_SECOND": GOLD,
            "EUROPE_OTHER": SKY,
            "AMERICAS": ORANGE,
            "ASIA_AFRICA": PINK,
            "OTHER": GREY,
        }.get(comp.group, GREY)
        print(
            f"  {WHITE}{comp.league_id:>4}{RESET}  "
            f"{comp.name:<38} "
            f"{GREY}Tier {comp.tier}{RESET} — "
            f"{group_color}{comp.group}{RESET}"
        )


def display_help() -> None:
    print_section("Commandes disponibles", CYAN)
    rows = [
        ("07", "Jour seul → mois+année détectés automatiquement"),
        ("07/12", "Jour+mois explicites (année courante)"),
        ("07/12/2026", "Date complète (priorité maximale)"),
        ("today", "Matchs du jour"),
        ("yesterday", "Matchs d'hier"),
        ("tomorrow", "Matchs de demain"),
        ("refresh", "Reconstruire les données et réentraîner"),
        ("status", "État du cache et des modèles"),
        ("competitions", "Afficher les ligues suivies"),
        ("clear", "Effacer l'écran"),
        ("help", "Afficher cette aide"),
        ("quit / exit / q", "Quitter"),
    ]
    for cmd, desc in rows:
        print(f"  {YELLOW}{cmd:<16s}{RESET} {desc}")


def display_status(state: Dict[str, Any]) -> None:
    print_section("État du système", CYAN)

    ml_models = state.get("ml_models")
    pb_models = state.get("pb_models")
    df_past = state.get("df_past")
    pipeline = state.get("pipeline")
    weights = state.get("weights") or {}

    n_ml = len(ml_models) if isinstance(ml_models, dict) else 0
    n_pb = len(pb_models) if isinstance(pb_models, list) else 0

    try:
        n_rows = int(len(df_past)) if df_past is not None else 0
    except Exception:
        n_rows = 0

    print(f"  {SKY}Cache :{RESET} {CACHE_DIR}")
    print(f"  {SKY}Checkpoints :{RESET} {CHECKPOINT_DIR}")
    print(
        f"  {SKY}Persistance :{RESET} "
        f"{'PERMANENTE' if CACHE_NEVER_EXPIRES else 'temporaire'}"
    )
    print(
        f"  {SKY}Manifest :{RESET} "
        f"{'présent' if MANIFEST_FILE.exists() else 'absent'}"
    )
    print(f"  {SKY}Schéma :{RESET} {ARTIFACT_SCHEMA_VERSION}")
    print(f"  {SKY}Fingerprint :{RESET} {CONFIG_FINGERPRINT[:16]}...")
    print(f"  {SKY}Source :{RESET} Bzzoiro")
    print(f"  {SKY}Tokens :{RESET} {TOKEN_COUNT}")
    print(
        f"  {SKY}Workers :{RESET} {BZZOIRO_WORKERS_PER_KEY}/clé "
        f"(max {BZZOIRO_MAX_WORKERS})"
    )
    print(
        f"  {SKY}Saisons lookback :{RESET} {HISTORICAL_SEASONS_LOOKBACK} | "
        f"xG : {'OUI' if BZZOIRO_ENRICH_XG else 'NON'}"
    )

    print()
    print(f"  {LIME}Matchs historiques :{RESET} {n_rows}")
    print(f"  {LIME}Modèles ML :{RESET} {n_ml}")
    print(f"  {LIME}Modèles Penaltyblog :{RESET} {n_pb}")
    print(
        f"  {LIME}Pipeline :{RESET} "
        f"{'OK' if pipeline is not None else 'absent'}"
    )

    if isinstance(weights, dict) and weights:
        temperature = weights.get("__temperature__")
        temperature_validated = weights.get("__temperature_validated__")
        if temperature is not None:
            try:
                temp_str = f"{float(temperature):.4f}"
                val_str = (
                    "validée"
                    if temperature_validated is True
                    else "non validée (valeur par défaut)"
                )
                print(f"  {LIME}Température :{RESET} {temp_str} ({val_str})")
            except (TypeError, ValueError):
                pass

        test_ll = weights.get("__test_logloss__")
        test_acc = weights.get("__test_accuracy__")
        if test_ll is not None:
            try:
                print(f"  {LIME}Test LogLoss :{RESET} {float(test_ll):.4f}")
            except (TypeError, ValueError):
                pass
        if test_acc is not None:
            try:
                print(
                    f"  {LIME}Test Accuracy :{RESET} "
                    f"{float(test_acc) * 100:.1f}%"
                )
            except (TypeError, ValueError):
                pass

        calibration_status_map = weights.get("__calibration_status_map__")
        if isinstance(calibration_status_map, dict) and calibration_status_map:
            print()
            print(f"  {SKY}Statuts de calibration :{RESET}")
            for key, status in calibration_status_map.items():
                try:
                    print(f"    {GREY}{key}{RESET} : {status}")
                except Exception:
                    continue

    print()
    if n_rows >= MIN_MATCHES_FOR_TRAINING and (n_ml > 0 or n_pb > 0):
        print(f"  {GREEN}Statut : prêt pour la prédiction{RESET}")
    else:
        print(
            f"  {YELLOW}Statut : mode dégradé "
            f"(données ou modèles insuffisants){RESET}"
        )


def _handle_sigint(signum: int, frame: Any) -> None:
    if _SHUTDOWN_FLAG["requested"]:
        print(f"\n{RED}Arrêt forcé.{RESET}")
        os._exit(130)
    _SHUTDOWN_FLAG["requested"] = True
    print(
        f"\n{YELLOW}Interruption détectée. "
        f"Appuyez de nouveau sur Ctrl+C pour forcer, ou tapez 'quit'.{RESET}"
    )


def _handle_sigterm(signum: int, frame: Any) -> None:
    logger.info("SIGTERM reçu, arrêt propre.")
    print(f"\n{YELLOW}Arrêt demandé.{RESET}")
    sys.exit(0)


def _install_signal_handlers() -> None:
    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (ValueError, OSError):
        pass
    try:
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (ValueError, OSError, AttributeError):
        pass


def _safe_reload_models(
    state: Dict[str, Any],
    force_refresh: bool,
) -> bool:
    try:
        result = load_or_build_data_and_models(force_refresh=force_refresh)
    except TypeError as exc:
        logger.error(
            "Signature de load_or_build_data_and_models incompatible : %s", exc
        )
        logger.debug(traceback.format_exc())
        print(
            f"{RED}Signature incompatible de load_or_build_data_and_models : "
            f"{exc}{RESET}"
        )
        return False
    except Exception as exc:
        logger.error("Échec du chargement des modèles : %s", exc)
        logger.debug(traceback.format_exc())
        print(f"{RED}Échec du chargement des modèles : {exc}{RESET}")
        return False

    if not isinstance(result, tuple) or len(result) != _TUPLE_LEN_EXPECTED:
        logger.error(
            "Signature inattendue de load_or_build_data_and_models : %r",
            type(result),
        )
        print(f"{RED}Signature de chargement invalide.{RESET}")
        return False

    ml_models, pb_models, pipeline, df_past, weights = result

    df_empty = df_past is None or getattr(df_past, "empty", True)
    if df_empty:
        logger.warning("Historique vide, les prédictions seront dégradées.")
        print(f"{YELLOW}⚠️  Aucun historique exploitable.{RESET}")
    else:
        try:
            n_rows = int(len(df_past))
        except Exception:
            n_rows = -1
        if 0 <= n_rows < MIN_MATCHES_FOR_TRAINING:
            logger.warning(
                "Historique trop petit pour l'entraînement (%d < %d).",
                n_rows,
                MIN_MATCHES_FOR_TRAINING,
            )
            print(
                f"{YELLOW}⚠️  Historique limité "
                f"({n_rows} matchs < {MIN_MATCHES_FOR_TRAINING}).{RESET}"
            )
        else:
            print(f"{GREEN}📚 Historique chargé : {n_rows} matchs.{RESET}")

    if not ml_models and not pb_models:
        logger.warning("Aucun modèle entraîné disponible.")
        print(f"{YELLOW}⚠️  Aucun modèle entraîné.{RESET}")
    else:
        n_ml = len(ml_models) if isinstance(ml_models, dict) else 0
        n_pb = len(pb_models) if isinstance(pb_models, list) else 0
        print(
            f"{GREEN}🤖 Modèles actifs : {n_ml} ML + {n_pb} Penaltyblog.{RESET}"
        )

    if weights is None:
        weights = {}

    state["ml_models"] = ml_models
    state["pb_models"] = pb_models
    state["pipeline"] = pipeline
    state["df_past"] = df_past
    state["weights"] = weights
    return True


def _predict_date(state: Dict[str, Any], date_iso: str) -> bool:
    try:
        predict_for_date(
            date_iso,
            state.get("ml_models"),
            state.get("pb_models"),
            state.get("pipeline"),
            state.get("df_past"),
            state.get("weights", {}),
        )
        return True
    except TypeError as exc:
        logger.error(
            "Signature de predict_for_date incompatible pour %s : %s",
            date_iso,
            exc,
        )
        logger.debug(traceback.format_exc())
        print(
            f"{RED}Signature incompatible de predict_for_date : {exc}{RESET}"
        )
        return False
    except Exception as exc:
        logger.error("Erreur de prédiction pour %s : %s", date_iso, exc)
        logger.debug(traceback.format_exc())
        print(f"{RED}Erreur lors de la prédiction : {exc}{RESET}")
        return False


def run_interactive(state: Dict[str, Any]) -> int:
    stage_print(
        f"{CYAN}🤖 GOANGEL PRÊT — Tapez un jour (ex: {YELLOW}07{RESET}{CYAN}) "
        f"ou une date complète ({YELLOW}07/12/2026{RESET}{CYAN}). "
        f"Tapez {YELLOW}help{RESET}{CYAN} pour l'aide.{RESET}"
    )
    while True:
        try:
            user_input = input(
                f"\n{GOLD}📅 Date ou commande "
                f"({YELLOW}quit{RESET}{GOLD} pour quitter) : {RESET}"
            )
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GREY}Au revoir.{RESET}")
            return 0

        if _SHUTDOWN_FLAG["requested"]:
            print(f"{YELLOW}Arrêt demandé.{RESET}")
            return 0

        if user_input is None:
            continue

        user_input = user_input.strip()
        if not user_input:
            continue

        ui = user_input.lower()

        if ui in _QUIT_COMMANDS:
            print(f"{GREY}Fermeture de GOANGEL.{RESET}")
            return 0

        if ui in _CLEAR_COMMANDS:
            clear_screen()
            continue

        if ui in _HELP_COMMANDS:
            display_help()
            continue

        if ui in _COMPETITIONS_COMMANDS:
            display_competitions()
            continue

        if ui in _STATUS_COMMANDS:
            display_status(state)
            continue

        if ui in _REFRESH_COMMANDS:
            print(
                f"{CYAN}♻️  Reconstruction complète des données et modèles "
                f"en cours...{RESET}"
            )
            ok = _safe_reload_models(state, force_refresh=True)
            if ok:
                print(f"{GREEN}✅ Reconstruction terminée.{RESET}")
            continue

        date_iso, mode, reason = parse_date_smart(user_input)

        if date_iso is None:
            print(
                f"{RED}❌ Date non reconnue : {reason}.{RESET}\n"
                f"{GREY}   Formats acceptés : "
                f"'07' (jour seul), '07/12' (jour+mois), "
                f"'07/12/2026' (complet), "
                f"today/yesterday/tomorrow.{RESET}"
            )
            continue

        pretty = _pretty_iso(date_iso)
        mode_color = {
            "auto": GOLD,
            "day_month": SKY,
            "full": LIME,
            "today": PINK,
            "yesterday": PINK,
            "tomorrow": PINK,
        }.get(mode, GREY)

        print(
            f"\n{CYAN}🔍 Prédictions pour le {BOLD}{pretty}{RESET} "
            f"{GREY}({mode_color}{reason}{GREY}){RESET}"
        )
        _predict_date(state, date_iso)
        print()
        print(f"{GREY}" + "═" * _SEPARATOR_LEN + f"{RESET}")


def run_single_date(
    date_input: str,
    state: Dict[str, Any],
) -> int:
    date_iso, mode, reason = parse_date_smart(date_input)
    if date_iso is None:
        logger.error("Format de date invalide : %s", date_input)
        print(f"{RED}❌ Date non reconnue : {reason}.{RESET}")
        return 2

    pretty = _pretty_iso(date_iso)
    print(
        f"{CYAN}🔍 Prédictions pour le {BOLD}{pretty}{RESET} "
        f"{GREY}({reason}){RESET}"
    )
    ok = _predict_date(state, date_iso)
    return 0 if ok else 1


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="goangel",
        description=(
            "GOANGEL — Moteur de prédictions sportives multi-modèles (Bzzoiro)"
        ),
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Date : '07' (jour seul), '07/12' (jour+mois), "
            "'07/12/2026' (complet), 'today', 'tomorrow', 'yesterday'"
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force la reconstruction complète du cache et des modèles",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Affiche l'état du cache et des modèles puis quitte",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="N'affiche pas la bannière",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Réduit la sortie console au strict minimum",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    _install_signal_handlers()
    args = _parse_args(argv)

    if not args.no_banner and not args.quiet:
        print_banner()
    if not args.quiet:
        stage_print(f"{CYAN}🚀 DÉMARRAGE INITIAL{RESET}")
    logger.info(
        "Démarrage de GOANGEL (argv=%s)",
        argv if argv is not None else sys.argv[1:],
    )

    state: Dict[str, Any] = {
        "ml_models": None,
        "pb_models": None,
        "pipeline": None,
        "df_past": None,
        "weights": {},
    }

    if not _safe_reload_models(state, force_refresh=args.refresh):
        logger.critical("Arrêt : impossible de charger les modèles.")
        if not args.quiet:
            stage_print(
                f"{RED}❌ Erreur fatale lors du chargement des modèles.{RESET}"
            )
        return 1

    if args.status:
        display_status(state)
        return 0

    if args.date:
        return run_single_date(args.date, state)

    try:
        return run_interactive(state)
    except KeyboardInterrupt:
        print(f"\n{GREY}Au revoir.{RESET}")
        return 130
    except Exception as exc:
        logger.critical("Erreur non gérée : %s", exc)
        logger.debug(traceback.format_exc())
        print(f"{RED}Erreur inattendue : {exc}{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
