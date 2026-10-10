import shutil
from pathlib import Path
from datetime import datetime

p = Path("config.py")
backup = p.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
shutil.copy2(p, backup)
print(f"💾 Backup : {backup.name}")

src = p.read_text(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════════════
# 1. Remplacer TOP_60_LEAGUES
# ═══════════════════════════════════════════════════════════════════════
import re
pattern_top = re.compile(
    r'TOP_60_LEAGUES:\s*Dict\[int,\s*str\]\s*=\s*\{.*?\n\}',
    re.DOTALL,
)

new_top = '''TOP_60_LEAGUES: Dict[int, str] = {
    1: "Premier League",
    3: "La Liga",
    4: "Serie A",
    5: "Bundesliga",
    6: "Ligue 1",
    10: "Eredivisie",
    9: "Brasileirão Serie A",
    2: "Liga Portugal Betclic",
    11: "Trendyol Super Lig",
    13: "Scottish Premiership",
    14: "Pro League (BEL)",
    49: "J1 League",
    85: "Liga Profesional (ARG)",
    84: "Danish Superliga",
    15: "Super League (SUI)",
    12: "Championship (ENG)",
    89: "Ligue 2",
    38: "Segunda División",
    34: "Brasileirão Serie B",
    18: "MLS",
    19: "Liga MX Apertura",
    20: "Liga MX Clausura",
    17: "Saudi Pro League",
    53: "Botola Pro",
    47: "Tunisian Ligue 1",
    86: "League One (ENG)",
    87: "League Two (ENG)",
    8: "Europa League",
    83: "Conference League",
}'''

if not pattern_top.search(src):
    raise SystemExit("❌ TOP_60_LEAGUES introuvable")

src = pattern_top.sub(new_top, src, count=1)
print("✅ TOP_60_LEAGUES remplacé (29 ligues)")

# ═══════════════════════════════════════════════════════════════════════
# 2. Remplacer _LEAGUE_GROUPS
# ═══════════════════════════════════════════════════════════════════════
pattern_groups = re.compile(
    r'_LEAGUE_GROUPS:\s*Dict\[str,\s*List\[int\]\]\s*=\s*\{.*?\n\}',
    re.DOTALL,
)

new_groups = '''_LEAGUE_GROUPS: Dict[str, List[int]] = {
    "EUROPE_TOP5": [1, 3, 4, 5, 6],
    "EUROPE_CUP": [8, 83],
    "EUROPE_SECOND": [12, 86, 87, 89, 38],
    "EUROPE_OTHER": [10, 2, 11, 13, 14, 84, 15],
    "AMERICAS": [9, 34, 18, 19, 20, 85],
    "ASIA_AFRICA": [49, 17, 53, 47],
}'''

if not pattern_groups.search(src):
    raise SystemExit("❌ _LEAGUE_GROUPS introuvable")

src = pattern_groups.sub(new_groups, src, count=1)
print("✅ _LEAGUE_GROUPS remplacé (6 groupes, 29 IDs)")

# ═══════════════════════════════════════════════════════════════════════
# 3. Remplacer COMPETITION_GROUP_ORDER
# ═══════════════════════════════════════════════════════════════════════
pattern_order = re.compile(
    r'COMPETITION_GROUP_ORDER:\s*Tuple\[str,\s*\.\.\.\]\s*=\s*\(.*?\)',
    re.DOTALL,
)

new_order = '''COMPETITION_GROUP_ORDER: Tuple[str, ...] = (
    "EUROPE_TOP5",
    "EUROPE_CUP",
    "EUROPE_SECOND",
    "EUROPE_OTHER",
    "AMERICAS",
    "ASIA_AFRICA",
    "OTHER",
)'''

if pattern_order.search(src):
    src = pattern_order.sub(new_order, src, count=1)
    print("✅ COMPETITION_GROUP_ORDER mis à jour (EUROPE_CUP ajouté)")
else:
    print("⚠️  COMPETITION_GROUP_ORDER introuvable")

# ═══════════════════════════════════════════════════════════════════════
# 4. Ajouter EUROPE_CUP dans REALISTIC_*_BY_GROUP
# ═══════════════════════════════════════════════════════════════════════
def add_group(src, pattern, new_entry):
    m = re.search(pattern, src, re.DOTALL)
    if not m:
        return src, False
    block = m.group(0)
    if "EUROPE_CUP" in block:
        return src, False
    new_block = block.replace("{\n", "{\n" + new_entry + "\n", 1)
    return src.replace(block, new_block, 1), True

src, ok1 = add_group(
    src,
    r'REALISTIC_HOME_LAMBDA_BY_GROUP:\s*Dict\[str,\s*float\]\s*=\s*\{.*?\n\}',
    '    "EUROPE_CUP": 1.42,',
)
src, ok2 = add_group(
    src,
    r'REALISTIC_AWAY_LAMBDA_BY_GROUP:\s*Dict\[str,\s*float\]\s*=\s*\{.*?\n\}',
    '    "EUROPE_CUP": 1.18,',
)
src, ok3 = add_group(
    src,
    r'REALISTIC_DRAW_RATE_BY_GROUP:\s*Dict\[str,\s*float\]\s*=\s*\{.*?\n\}',
    '    "EUROPE_CUP": 0.25,',
)
src, ok4 = add_group(
    src,
    r'REALISTIC_HOME_ADVANTAGE_BY_GROUP:\s*Dict\[str,\s*float\]\s*=\s*\{.*?\n\}',
    '    "EUROPE_CUP": 55.0,',
)
print(f"✅ REALISTIC_* : HOME={ok1} AWAY={ok2} DRAW={ok3} ADV={ok4}")

p.write_text(src, encoding="utf-8")
print()
print("🎉 Patches config.py appliqués")

# ═══════════════════════════════════════════════════════════════════════
# Vérification
# ═══════════════════════════════════════════════════════════════════════
import subprocess, sys
r = subprocess.run(
    [sys.executable, "-c",
     "import config; "
     "print(f'Ligues : {len(config.TOP_60_LEAGUES)}'); "
     "print(f'Groupes : {list(config.COMPETITION_GROUPS.keys())}'); "
     "print(f'Ordre groupes : {config.COMPETITION_GROUP_ORDER}')"],
    capture_output=True, text=True,
)
print(r.stdout.strip() or r.stderr.strip()[:500])
