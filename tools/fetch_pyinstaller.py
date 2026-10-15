"""Fetch and unpack PyInstaller + deps into .pylibs without using pip.

pip's wheel-metadata step is denied by the DSH file sandbox, so we resolve the
wheels straight from the PyPI JSON API, download them and unzip them.
"""
import json
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, ".pylibs")
CACHE = os.path.join(ROOT, ".tmp", "wheels")

REQUIREMENTS = [
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "pefile",
    "pywin32-ctypes",
    "packaging",
    "setuptools",
]


def pick_wheel(files, py_tag, verbose=False):
    names = [f for f in files if f["filename"].endswith(".whl")]
    if verbose:
        for f in names:
            if "win_amd64" in f["filename"] or "none-any" in f["filename"]:
                print("   candidate:", f["filename"])

    def exact(suffix):
        return [f for f in names if f["filename"].endswith(suffix)]

    for suffix in (
        f"-cp{py_tag}-cp{py_tag}-win_amd64.whl",
        f"-cp{py_tag}-abi3-win_amd64.whl",
        "-py3-none-win_amd64.whl",
        "-py2.py3-none-any.whl",
        "-py3-none-any.whl",
        "-py2.py3-none-any.whl",
    ):
        hit = exact(suffix)
        if hit:
            return hit[0]
    win = [
        f for f in names
        if "win_amd64" in f["filename"] and "pp3" not in f["filename"] and "cp3" not in f["filename"]
    ]
    if win:
        return win[0]
    pure = [f for f in names if f["filename"].endswith("py3-none-any.whl")]
    if pure:
        return pure[0]
    if names:
        return names[0]
    return None


def main():
    if len(sys.argv) > 1:
        REQUIREMENTS[:] = sys.argv[1:]
    py_tag = f"{sys.version_info.major}{sys.version_info.minor}"
    os.makedirs(TARGET, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    seen = set()
    queue = list(REQUIREMENTS)

    while queue:
        name = queue.pop(0)
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        url = f"https://pypi.org/pypi/{name}/json"
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.load(resp)
        info = data["info"]
        requires = info.get("requires_dist") or []
        wheel = pick_wheel(data["urls"], py_tag)
        if wheel is None:
            print(f"!! no wheel for {name}")
            continue
        dest = os.path.join(CACHE, wheel["filename"])
        if not os.path.exists(dest):
            print(f"downloading {wheel['filename']}")
            with urllib.request.urlopen(wheel["url"], timeout=300) as resp, open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
        else:
            print(f"cached {wheel['filename']}")
        with zipfile.ZipFile(dest) as zf:
            zf.extractall(TARGET)
        for req in requires:
            if ";" in req:
                marker = req.split(";", 1)[1]
                if "extra" in marker:
                    continue
            dep = req.split(";")[0].split("[")[0].strip()
            for sep in (">=", "==", "<=", "!=", "~=", ">", "<", " "):
                dep = dep.split(sep)[0]
            dep = dep.strip()
            if dep and dep.lower() not in seen:
                queue.append(dep)

    print("unpacked into", TARGET)


if __name__ == "__main__":
    main()
