from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_JSON = ROOT / "models" / "model.json"
REQUIRED_LICENSES = ("LICENSE-XuanmuSec.txt", "LICENSE-LFM1.0.txt")
# Apache-2.0.txt is the full text that LICENSE-XuanmuSec.txt points to, so the
# package is not self-consistent without it.
ALWAYS_BUNDLED_LICENSES = ("Apache-2.0.txt",)
# Bundled only when llama.cpp binaries are shipped with the model.
RUNTIME_LICENSES = ("LICENSE-llama.cpp.txt",)
CHUNK = 8 * 1024 * 1024
ZIP_STORE_THRESHOLD = 64 * 1024 * 1024


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_gguf_header(path: Path) -> tuple[int, int, int]:
    size = path.stat().st_size
    if size < 24:
        raise ValueError(f"文件过小，不是完整 GGUF：{size} 字节")
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:4] != b"GGUF":
        raise ValueError("文件头不是 GGUF 魔数")
    version, tensor_count, kv_count = struct.unpack_from("<IQQ", header, 4)
    if not 1 <= version <= 3:
        raise ValueError(f"不支持的 GGUF 版本：{version}（预期 1-3）")
    if tensor_count > 100_000_000:
        raise ValueError(f"张量数量异常：{tensor_count}")
    if kv_count > 1_000_000:
        raise ValueError(f"元数据条目数量异常：{kv_count}")
    if size < 64 * 1024:
        raise ValueError(f"模型体积异常偏小：{human_size(size)}")
    return version, tensor_count, kv_count


def sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return cleaned or "SecOne-model"


def collect_licenses(
    extra: list[Path], allow_missing: bool, include_runtime: bool = False
) -> list[Path]:
    licenses: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        licenses.append(resolved)

    wanted = list(REQUIRED_LICENSES) + list(ALWAYS_BUNDLED_LICENSES)
    if include_runtime:
        wanted += list(RUNTIME_LICENSES)

    missing_bundled: list[str] = []
    for name in wanted:
        candidate = ROOT / "licenses" / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            add(candidate)
        elif name in ALWAYS_BUNDLED_LICENSES or (
            include_runtime and name in RUNTIME_LICENSES
        ):
            missing_bundled.append(name)
    for item in extra:
        path = item.resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"许可文件不存在或为空：{item}")
        add(path)

    names = {path.name for path in licenses}
    missing = [name for name in REQUIRED_LICENSES if name not in names]
    if missing and not allow_missing:
        raise SystemExit(
            "缺少模型许可文件：" + ", ".join(missing) + "\n"
            "请把上游提供的许可文本放入 licenses/，或通过 --license 指定；"
            "确认条款不适用时才使用 --allow-missing-model-licenses。"
        )
    if missing:
        print("警告：缺失模型许可文件，已按 --allow-missing-model-licenses 继续：" + ", ".join(missing))
    if missing_bundled:
        raise SystemExit(
            "缺少随包分发所需的许可文本：" + ", ".join(missing_bundled) + "\n"
            "LICENSE-XuanmuSec.txt 引用了 Apache-2.0.txt 全文，"
            "分发 llama.cpp 二进制时也必须附带 LICENSE-llama.cpp.txt。"
        )
    return licenses


def write_manifest(package_dir: Path) -> Path:
    entries: list[tuple[str, str]] = []
    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(package_dir).as_posix()
        if relative == "SHA256SUMS.txt":
            continue
        entries.append((relative, sha256_file(path)))
    entries.sort(key=lambda item: item[0])
    manifest = package_dir / "SHA256SUMS.txt"
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        for relative, digest in entries:
            handle.write(f"{digest}  {relative}\n")
    print(f"校验清单：{manifest}（{len(entries)} 个文件）")
    return manifest


def make_zip(package_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
        compresslevel=6,
    ) as archive:
        for path in sorted(package_dir.rglob("*")):
            if not path.is_file():
                continue
            archive.write(
                path,
                path.relative_to(package_dir.parent).as_posix(),
                compress_type=(
                    zipfile.ZIP_STORED
                    if path.stat().st_size >= ZIP_STORE_THRESHOLD
                    else zipfile.ZIP_DEFLATED
                ),
            )
    digest = sha256_file(zip_path)
    checksum = zip_path.with_suffix(zip_path.suffix + ".sha256")
    checksum.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8", newline="\n")
    print(f"ZIP 包：{zip_path}（{human_size(zip_path.stat().st_size)}）")
    print(f"ZIP 校验：{digest}")
    print(f"校验文件：{checksum}")


def copy_runtime(source: Path, target: Path) -> int:
    copied = 0
    for item in source.rglob("*"):
        if not item.is_file() or "__pycache__" in item.parts:
            continue
        destination = target / item.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        copied += 1
    return copied


def build(args: argparse.Namespace) -> Path:
    gguf = args.gguf.resolve()
    if not gguf.is_file():
        raise SystemExit(f"未找到 GGUF 文件：{gguf}")
    if gguf.suffix.lower() != ".gguf":
        print(f"警告：文件扩展名不是 .gguf：{gguf.name}")

    try:
        version, tensor_count, kv_count = read_gguf_header(gguf)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"GGUF 校验失败：{exc}") from exc
    size = gguf.stat().st_size
    print(f"GGUF 校验通过：v{version}，张量 {tensor_count}，元数据 {kv_count}，{human_size(size)}")
    if version < 2:
        print("警告：GGUF v1 较旧，请确认目标 llama.cpp 版本仍支持。")

    licenses = collect_licenses(
        [Path(item) for item in args.license],
        args.allow_missing_model_licenses,
        include_runtime=bool(args.runtime_dir),
    )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    metadata: dict = {}
    model_json = args.model_json.resolve()
    if model_json.is_file():
        metadata = json.loads(model_json.read_text(encoding="utf-8"))
    else:
        print(f"提示：未找到 {model_json}，将生成最小元数据。")

    display_name = str(metadata.get("display_name") or gguf.stem)
    display_slug = sanitize_name(display_name)
    if display_slug == "SecOne-model":
        # Non-Latin display names sanitize to nothing; the weights filename is
        # the only remaining stable identity for the package.
        display_slug = sanitize_name(gguf.stem)
    quantization = str(metadata.get("quantization") or "").strip()
    if quantization and not display_slug.lower().endswith(quantization.lower()):
        default_name = f"SecOne-model-{display_slug}-{quantization}"
    else:
        default_name = f"SecOne-model-{display_slug}"
    package_name = sanitize_name(args.name or default_name)

    package_dir = output / package_name
    zip_path = output / f"{package_name}.zip"
    if package_dir.exists() or zip_path.exists():
        if not args.force:
            raise SystemExit(f"输出已存在：{package_dir} 或 {zip_path}。使用 --force 覆盖。")
        shutil.rmtree(package_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        zip_path.with_suffix(zip_path.suffix + ".sha256").unlink(missing_ok=True)

    model_dir = package_dir / "models"
    license_dir = package_dir / "licenses"
    model_dir.mkdir(parents=True)
    license_dir.mkdir(parents=True)

    print(f"计算 SHA256 ...")
    digest = sha256_file(gguf)
    print(f"SHA256：{digest}")
    shutil.copy2(gguf, model_dir / gguf.name)

    metadata.update(
        {
            "filename": gguf.name,
            "expected_size_bytes": size,
            "sha256": digest,
        }
    )
    if quantization:
        metadata["quantization"] = quantization
    model_dir.joinpath("model.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    for license_path in licenses:
        shutil.copy2(license_path, license_dir / license_path.name)
    for extra_name in ("README.md",):
        candidate = ROOT / "licenses" / extra_name
        if candidate.is_file() and not (license_dir / extra_name).exists():
            shutil.copy2(candidate, license_dir / extra_name)
    notices = ROOT / "THIRD_PARTY_NOTICES.md"
    if notices.is_file():
        shutil.copy2(notices, package_dir / notices.name)

    runtime_count = 0
    if args.runtime_dir:
        runtime_source = args.runtime_dir.resolve()
        if not runtime_source.is_dir():
            raise SystemExit(f"运行组件目录不存在：{runtime_source}")
        runtime_count = copy_runtime(runtime_source, package_dir / "runtime")
        print(f"运行组件：{runtime_count} 个文件 -> {package_dir / 'runtime'}")
        if runtime_count and not (package_dir / "runtime" / "llama-server.exe").is_file():
            print("警告：运行组件中未找到 llama-server.exe，请在设置页确认运行时路径。")

    install_note = (
        "SecOne 模型包\n"
        "=============\n\n"
        "安装方法：将本目录中的 models/（以及可选的 runtime/）合并到 SecOne 安装目录，\n"
        "保持与 SecOne.exe 同级。默认路径为：\n"
        "  %LOCALAPPDATA%\\Programs\\SecOne\\models\\\n"
        "  %LOCALAPPDATA%\\Programs\\SecOne\\runtime\\\n\n"
        "校验文件完整性：\n"
        "  certutil -hashfile <文件> SHA256\n"
        "或对照 SHA256SUMS.txt。\n\n"
        "许可：模型权重同时受 XuanmuSec 的 Apache-2.0 声明与基座模型 LFM1.0 License 约束。\n"
        "分发或再发布前请逐项核对上游条款，保留 licenses/ 与 THIRD_PARTY_NOTICES.md。\n"
    )
    package_dir.joinpath("INSTALL.txt").write_text(install_note, encoding="utf-8", newline="\n")

    write_manifest(package_dir)
    print(f"模型包目录：{package_dir}")
    if not args.no_zip:
        make_zip(package_dir, zip_path)
    return package_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="校验 GGUF，并生成带许可文件与 SHA256 清单的 SecOne 模型包。"
    )
    parser.add_argument("--gguf", type=Path, default=ROOT / "models" / "XuanmuSec-v2-Q6_K.gguf")
    parser.add_argument("--runtime-dir", type=Path, default=None, help="llama.cpp 运行组件目录，如 runtime")
    parser.add_argument("--license", action="append", default=[], help="额外的许可文件，可重复")
    parser.add_argument("--model-json", type=Path, default=DEFAULT_MODEL_JSON)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "packages")
    parser.add_argument("--name", default="", help="包名，默认由模型名与量化方式生成")
    parser.add_argument("--no-zip", action="store_true", help="只生成目录，不压缩")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的同名目录与 ZIP")
    parser.add_argument(
        "--allow-missing-model-licenses",
        action="store_true",
        help="允许缺少 XuanmuSec / LFM1.0 许可文件（仅限确认条款不适用时）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"打包失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
