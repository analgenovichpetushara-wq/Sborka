import json, os, re, time, zipfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MC = "1.21.1"
API = "https://api.modrinth.com/v2"
OUT = Path(".")
requested = ["create","jei","jade","appleskin","mouse-tweaks","embeddium","oculus","modernfix","ferrite-core","entityculling","immediatelyfast","clumps","spark","betterf3","controlling","xaeros-minimap","xaeros-world-map","worldedit","create-deco","create-steam-n-rails","createaddition","create-framed","create-bells-and-whistles","copycats","chipped","framedblocks","handcrafted","supplementaries","moonlight","another-furniture","macaws-doors","macaws-windows","macaws-roofs","macaws-fences-and-walls","macaws-bridges","macaws-lights-and-lamps","macaws-trapdoors","macaws-paths-and-pavings","rechiseled","rechiseled-create","builders-delight","chisels-bits","immersive-aircraft","waystones","carry-on","light-overlay","polymorph","configured","catalogue","patchouli","architectury-api","cloth-config","resourceful-lib","bookshelf","balm","curios","tectonic","terralith","towns-and-towers","yungs-api","yungs-better-dungeons","yungs-better-mineshafts","yungs-better-strongholds","yungs-better-nether-fortresses","yungs-better-desert-temples","yungs-better-jungle-temples","yungs-better-witch-huts","better-archeology","regions-unexplored","immersive-melodies"]

cache = {}
selected = {}
missing = []
warnings = []

def get_json(url, params=None):
    key = url + ("?" + urlencode(params or {}) if params else "")
    if key in cache:
        return cache[key]
    req = Request(key, headers={"User-Agent": "NEON-TOKYO-pack-builder/1.0"})
    for attempt in range(4):
        try:
            with urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8"))
            cache[key] = data
            time.sleep(0.15)
            return data
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

def choose_version(slug):
    params = {
        "loaders": json.dumps(["neoforge"]),
        "game_versions": json.dumps([MC]),
    }
    versions = get_json(f"{API}/project/{slug}/version", params)
    if not versions:
        return None
    stable = [v for v in versions if v.get("version_type") == "release"]
    return (stable or versions)[0]

def project(slug):
    return get_json(f"{API}/project/{slug}")

def version_by_id(vid):
    return get_json(f"{API}/version/{vid}")

def add_version(v, source):
    vid = v["id"]
    if vid in selected:
        return
    files = v.get("files") or []
    if not files:
        warnings.append(f"{source}: version {v.get('version_number')} has no files")
        return
    primary = next((f for f in files if f.get("primary")), files[0])
    pslug = source
    try:
        p = project(pslug)
    except Exception:
        p = {"client_side":"required","server_side":"required","title":pslug}
    selected[vid] = {
        "version": v,
        "project": p,
        "file": primary,
        "slug": pslug,
    }
    for dep in v.get("dependencies", []):
        if dep.get("dependency_type") != "required":
            continue
        dep_vid = dep.get("version_id")
        dep_pid = dep.get("project_id")
        try:
            if dep_vid:
                dv = version_by_id(dep_vid)
                add_version(dv, dep_pid or dep_vid)
            elif dep_pid:
                dp = project(dep_pid)
                slug = dp.get("slug") or dep_pid
                dv = choose_version(slug)
                if dv:
                    add_version(dv, slug)
                else:
                    warnings.append(f"required dependency unavailable for 1.21.1 NeoForge: {slug}")
        except Exception as e:
            warnings.append(f"dependency resolution failed for {dep_pid or dep_vid}: {e}")

def neoforge_version():
    url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
    req = Request(url, headers={"User-Agent":"NEON-TOKYO-pack-builder/1.0"})
    with urlopen(req, timeout=45) as r:
        root = ET.fromstring(r.read())
    vals = [x.text for x in root.findall("./versioning/versions/version") if x.text]
    candidates = [x for x in vals if re.fullmatch(r"21\.1\.\d+", x)]
    if not candidates:
        raise RuntimeError("No NeoForge 21.1.x release found")
    return candidates[-1]

for slug in requested:
    try:
        v = choose_version(slug)
        if v:
            add_version(v, slug)
        else:
            missing.append(slug)
    except Exception as e:
        missing.append(f"{slug} ({e})")

files = []
for item in selected.values():
    f = item["file"]
    h = f.get("hashes", {})
    if not h.get("sha1") or not h.get("sha512"):
        warnings.append(f"missing required hashes: {item['slug']} {item['version'].get('version_number')}")
        continue
    env = {
        "client": item["project"].get("client_side", "required"),
        "server": item["project"].get("server_side", "required"),
    }
    files.append({
        "path": "mods/" + f["filename"],
        "hashes": {"sha1": h["sha1"], "sha512": h["sha512"]},
        "env": env,
        "downloads": [f["url"]],
        "fileSize": f["size"],
    })

nf = neoforge_version()
index = {
    "formatVersion": 1,
    "game": "minecraft",
    "versionId": "1.0.0",
    "name": "NEON TOKYO",
    "summary": "Minecraft 1.21.1 NeoForge city-building pack: cyberpunk neon + Japanese architecture + retrofuturist industry.",
    "files": sorted(files, key=lambda x: x["path"].lower()),
    "dependencies": {"minecraft": MC, "neoforge": nf},
}

(OUT / "modrinth.index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

pack = OUT / "NEON-TOKYO-1.0.0.mrpack"
with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr("modrinth.index.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")

report = [
    f"NEON TOKYO 1.0.0",
    f"Minecraft: {MC}",
    f"NeoForge: {nf}",
    f"Requested projects: {len(requested)}",
    f"Resolved mod files: {len(files)}",
    f"Resolved versions including dependencies: {len(selected)}",
]
if missing:
    report.append("Skipped/unavailable:")
    report.extend("  - " + x for x in missing)
if warnings:
    report.append("Warnings:")
    report.extend("  - " + x for x in warnings)
(OUT / "build-report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report))
if len(files) < 45:
    raise SystemExit("Too few compatible mods resolved; refusing to publish a broken-looking pack.")
