"""APK processing helper functions"""

import shutil
import tempfile
from pathlib import Path
import logging
import time
from typing import Dict, Tuple, Optional
import config
from apk_utils import (
    interactive_file_modification,
    load_patches_from_json,
    apply_file_patches,
    decompile_apk,
    compile_apk,
    align_apk,
    generate_key,
    sign_apk,
    install_apk_on_device
)
from merger import merge_apks
# Import SDK manager functions
from sdk_manager import ensure_tools_available, get_sdk_tool_paths


def create_work_paths(
    work_dir: Path,
    apk_name: str,
    timestamp: int
) -> Dict[str, Path]:
    """Create and return all working paths"""
    return {
        'decompiled': work_dir / f"{apk_name}_{timestamp}_decompiled",
        'unaligned': work_dir / f"{apk_name}_unaligned.apk",
        'aligned': work_dir / f"{apk_name}_aligned.apk",
        'keystore': work_dir / config.DEFAULT_KEYSTORE,
        'output': Path.cwd() / f"{apk_name}_signed.apk"
    }


def setup_working_directory(
    working_dir: str,
    apk_name: str
) -> Tuple[Path, bool]:
    """Set up and return working directory path and temp flag"""
    if working_dir:
        work_dir = Path(working_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        logging.info(f"Using working directory: {work_dir}")
        return work_dir, False
    else:
        work_dir = Path(tempfile.mkdtemp(prefix=config.TEMP_DIR_PREFIX))
        logging.info(f"Using temporary directory: {work_dir}")
        return work_dir, True


def apply_patches(args, decompiled_dir: Path) -> bool:
    """Apply patches to decompiled APK"""
    if args.interactive:
        interactive_file_modification(decompiled_dir)
        return True

    patches_file = Path(args.apk_file_patches)
    if not patches_file.exists():
        msg = f"APK file patches file not found: {patches_file}"
        logging.error(msg)
        print(f"Error: {msg}")
        print("Please provide a valid patches file or use -i")
        return False

    patches = load_patches_from_json(patches_file)
    apply_file_patches(decompiled_dir, patches)
    return True


def process_apk(args, work_dir: Path, apk_path: Path, tools_dir: Optional[Path]) -> int:
    """
    Process the APK file.

    Args:
        args: Parsed command-line arguments.
        work_dir: Working directory Path object.
        apk_path: Input APK Path object.
        tools_dir: Path to the user-provided tools directory (can be None if downloading).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        # --- Tool Discovery/Installation ---
        # Determine SDK root (might be None)
        sdk_root_path = Path(args.sdk_root).resolve(
        ) if args.sdk_root else config.DEFAULT_SDK_ROOT

        # Decide if tools need to be ensured/installed
        # This logic is now handled by the argument parser requiring --tools-dir or --download-tools
        # We pass the tools_dir (which can be None if --download-tools was exclusive) and download flag

        if not ensure_tools_available(
            tools_dir=tools_dir,  # This can be None if only --download-tools was used
            download_tools=args.download_tools,
            # Only pass SDK root if downloading
            sdk_root=sdk_root_path if args.download_tools else None,
            android_version=args.android_version if args.download_tools else None
        ):
            return 1  # Error already logged by ensure_tools_available

        # --- Resolve Tool Paths After Ensuring Availability ---
        # At this point, tools should be available either in tools_dir or installed in SDK

        # 1. Resolve apktool path
        # Priority: User-provided --apktool-path > tools_dir > Assume 'apktool' in PATH (less likely to work)
        if args.apktool_path:
            apktool_path_final = Path(args.apktool_path).resolve()
        elif tools_dir:
            apktool_path_final = tools_dir / config.APKTOOL_JAR
        else:
            # This case is unlikely due to argument parsing, but as a fallback
            logging.warning(
                "No explicit apktool path or tools directory provided. Assuming 'apktool' is in PATH.")
            # Just the filename, relies on PATH
            apktool_path_final = Path(config.APKTOOL_JAR)

        # 2. Resolve zipalign and apksigner paths
        # Priority: User-provided --zipalign-path/--apksigner-path > Found in SDK > Fallbacks
        zipalign_path_final = None
        apksigner_path_final = None

        # Use user-provided paths if given
        if args.zipalign_path:
            zipalign_path_final = Path(args.zipalign_path).resolve()
        if args.apksigner_path:
            apksigner_path_final = Path(args.apksigner_path).resolve()

        # If not provided by user, try to find in SDK (only relevant if SDK tools were managed)
        if (not zipalign_path_final or not apksigner_path_final) and sdk_root_path.exists():
            logging.info("Attempting to locate SDK tools...")
            # Try to get paths from the SDK manager
            zp_sdk, ap_sdk = get_sdk_tool_paths(
                sdk_root_path, args.android_version)
            if not zipalign_path_final and zp_sdk and zp_sdk.exists():
                zipalign_path_final = zp_sdk
                logging.info(f"Found zipalign in SDK: {zipalign_path_final}")
            if not apksigner_path_final and ap_sdk and ap_sdk.exists():
                apksigner_path_final = ap_sdk
                logging.info(f"Found apksigner in SDK: {apksigner_path_final}")

        # Final validation of critical tool paths
        if not apktool_path_final or not apktool_path_final.exists():
            msg = f"apktool not found at resolved path: {apktool_path_final}"
            logging.error(msg)
            print(f"Error: {msg}")
            return 1

        if not zipalign_path_final or not zipalign_path_final.exists():
            msg = f"zipalign not found at resolved path: {zipalign_path_final}. Ensure it's available or provide --zipalign-path."
            logging.error(msg)
            print(f"Error: {msg}")
            return 1

        if not apksigner_path_final or not apksigner_path_final.exists():
            msg = f"apksigner not found at resolved path: {apksigner_path_final}. Ensure it's available or provide --apksigner-path."
            logging.error(msg)
            print(f"Error: {msg}")
            return 1

        # --- Processing Steps ---
        # Set up file paths
        timestamp = int(time.time())
        paths = create_work_paths(work_dir, apk_path.stem, timestamp)

        logging.info("Starting APK processing...")

        # 1. Decompile APK
        decompile_apk(str(apk_path), paths['decompiled'], apktool_path_final)

        # 2. Apply patches
        if not apply_patches(args, paths['decompiled']):
            return 1

        # 3. Compile modified APK
        compile_apk(paths['decompiled'],
                    paths['unaligned'], apktool_path_final)

        # 4. Align APK
        align_apk(paths['unaligned'], paths['aligned'], zipalign_path_final)

        # 5. Generate key if needed
        if not args.keystore:
            generate_key(
                paths['keystore'],
                args.alias,
                args.password,
                config.KEYTOOL_BINARY_PATH
            )
            keystore_path = paths['keystore']
        else:
            keystore_path = Path(args.keystore).resolve()

        # 6. Sign APK
        sign_apk(
            paths['aligned'],
            keystore_path,
            args.alias,
            args.password,
            apksigner_path_final
        )

        # 7. Handle merging or finalize output
        final_apk_path = paths['aligned']  # Default to aligned APK path
        if args.merge_with:
            temp_merged_apk = work_dir / f"{apk_path.stem}_temp_merged.apk"
            success = merge_apks(
                # Use the signed/aligned APK as base for merging
                base_apk=str(paths['aligned']),
                unsigned_apks=args.merge_with,
                output_apk=str(temp_merged_apk),
                apkeditor_jar=args.apkeditor_jar,
                verbose=args.verbose  # Pass verbose flag if your merge_apks supports it
            )
            if not success:
                logging.error("APK merging failed")
                return 1
            final_apk_path = temp_merged_apk  # Update path to the merged APK

        # 8. Move final APK to output location
        out_path = Path(args.output) if args.output else paths['output']
        shutil.move(str(final_apk_path), str(out_path))
        action_desc = "Merged and signed" if args.merge_with else "Signed"
        logging.info(f"{action_desc} APK created at: {out_path}")

        # 9. Install APK on device if requested
        if args.install or args.install_on_device:
            install_apk_on_device(str(out_path), args.install_on_device)

        return 0

    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        return 1
