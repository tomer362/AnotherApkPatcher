#!/usr/bin/env python3

"""Main script for APK patching tool"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

import config
from apk_processor import process_apk, setup_working_directory


def setup_logging(debug: bool = False) -> None:
    """Configure logging settings"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.DEFAULT_LOG_FILE),
            logging.StreamHandler()
        ]
    )


def setup_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser"""
    parser = argparse.ArgumentParser(
        description=(
            "Tool for patching APK files with interactive or "
            "JSON-based file modifications"
        )
    )
    parser.add_argument(
        "apk_path",
        help="Path to the APK file to patch"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Enable interactive file modification mode"
    )
    parser.add_argument(
        "-f", "--apk-file-patches",
        default=str(config.DEFAULT_PATCHES_FILE),
        help=f"Path to the JSON file containing APK file patches (default: {config.DEFAULT_PATCHES_FILE})"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path for the patched APK file"
    )
    parser.add_argument(
        "-w", "--working-dir",
        help="Working directory for unpacked APK files. If not specified, "
             "a temporary directory will be used"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install the patched APK on the default device"
    )
    parser.add_argument(
        "--install-on-device",
        help="Device serial number to install the APK on"
    )
    # --- Tool Paths ---
    # These now have defaults assuming tools are in --tools-dir
    # The actual resolution happens in apk_processor.process_apk
    parser.add_argument(
        "--apktool-path",
        # No default here, resolved dynamically or via --tools-dir
        help="Path to apktool executable/jar (default: <tools-dir>/apktool.jar)"
    )
    parser.add_argument(
        "--zipalign-path",
        # No default here, resolved dynamically or via SDK
        help="Path to zipalign executable (default: found in SDK or PATH)"
    )
    parser.add_argument(
        "--apksigner-path",
        # No default here, resolved dynamically or via SDK
        help="Path to apksigner.bat (default: found in SDK)"
    )
    # --- Signing ---
    parser.add_argument(
        "--alias",
        default=config.DEFAULT_ALIAS,
        help=f"Keystore alias for signing (default: {config.DEFAULT_ALIAS})"
    )
    parser.add_argument(
        "--password",
        default=config.DEFAULT_PASSWORD,
        help=f"Keystore password for signing (default: {config.DEFAULT_PASSWORD})"
    )
    parser.add_argument(
        "--keystore",
        help="Path to existing keystore file (will generate if not provided)"
    )
    # --- Merging ---
    parser.add_argument(
        "--merge-with",
        nargs="+",
        help="Additional APK files to merge with the patched APK"
    )
    parser.add_argument(
        "--apkeditor-jar",
        default=str(config.APKEDITOR_JAR_DEFAULT),
        help=f"Path to APKEditor jar file (default: {config.APKEDITOR_JAR_DEFAULT})"
    )
    # --- Logging ---
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    # --- Tool Management ---
    # Make --tools-dir required unless --download-tools is used
    tool_management_group = parser.add_argument_group('tool management')
    tool_mgmt_exclusive = tool_management_group.add_mutually_exclusive_group(
        required=True)
    tool_mgmt_exclusive.add_argument(
        "--tools-dir", "-t",
        help="REQUIRED: Directory containing tools (apktool.jar) or where tools will be downloaded."
    )
    tool_mgmt_exclusive.add_argument(
        "--download-tools", "-d",
        action="store_true",
        help="Automatically download missing tools (requires --sdk-root)."
    )

    parser.add_argument(
        "--sdk-root", "-s",
        help=f"Android SDK root directory for tool installation (default: {config.DEFAULT_SDK_ROOT})"
    )
    parser.add_argument(
        "--android-version", "-V", default=config.DEFAULT_ANDROID_VERSION,
        help=f"Android API version for build tools (default: {config.DEFAULT_ANDROID_VERSION})"
    )

    return parser


def main() -> int:
    """Main entry point"""
    try:
        parser = setup_argument_parser()
        args = parser.parse_args()
        setup_logging(args.debug)

        # --- Post-Parse Validation ---
        # If --download-tools is specified, --sdk-root becomes mandatory
        if args.download_tools and not args.sdk_root:
            parser.error(
                "--download-tools requires --sdk-root to be specified.")

        # Validate APK path
        apk_path = Path(args.apk_path)
        if not apk_path.exists():
            msg = f"APK file not found: {apk_path}"
            logging.error(msg)
            print(f"Error: {msg}")
            return 1

        # Resolve tools directory path (will be None if --download-tools was used exclusively)
        tools_dir = Path(args.tools_dir).resolve() if args.tools_dir else None
        if tools_dir:
            # Ensure the provided tools directory exists if it's supposed to be used
            if not args.download_tools:  # Only enforce existence if not downloading
                if not tools_dir.exists():
                    msg = f"Provided tools directory does not exist: {tools_dir}"
                    logging.error(msg)
                    print(f"Error: {msg}")
                    print("Please create the directory or use --download-tools.")
                    return 1
                # Basic check for apktool in the directory
                apktool_candidate = tools_dir / config.APKTOOL_JAR
                if not apktool_candidate.exists():
                    msg = f"apktool.jar not found in provided tools directory: {tools_dir}"
                    logging.error(msg)
                    print(f"Error: {msg}")
                    print(
                        "Please place apktool.jar in the directory or use --download-tools.")
                    return 1
            else:
                # If downloading, just ensure parent exists or create tools dir
                tools_dir.mkdir(parents=True, exist_ok=True)

        # Set up working directory
        work_dir, is_temp = setup_working_directory(
            args.working_dir, apk_path.stem
        )

        try:
            return process_apk(args, work_dir, apk_path, tools_dir)
        finally:
            # Clean up temporary directory if used
            if is_temp:
                logging.info(f"Cleaning up temporary directory: {work_dir}")
                shutil.rmtree(str(work_dir))

    except SystemExit:
        # argparse calls sys.exit on error, let it propagate
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
