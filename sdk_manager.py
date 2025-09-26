# sdk_manager.py
"""Functions for managing the Android SDK and locating tools."""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional, Tuple
import urllib.request
import urllib.error
import config


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)


def get_platform_suffix() -> str:
    """Get platform-specific suffix for commandline tools"""
    system = platform.system().lower()
    if system == "windows":
        return "win"
    elif system == "darwin":
        return "mac"
    else:
        return "linux"


def download_file(url: str, destination: Path) -> None:
    """Download a file from URL to destination"""
    logging.info(f"Downloading {url} to {destination}")
    try:
        urllib.request.urlretrieve(url, str(destination))
        logging.info("Download completed successfully")
    except urllib.error.URLError as e:
        logging.error(f"Failed to download file: {e}")
        raise


def extract_zip(file_path: Path, extract_to: Path) -> None:
    """Extract ZIP file to destination"""
    logging.info(f"Extracting {file_path} to {extract_to}")
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        logging.info("Extraction completed successfully")
    except zipfile.BadZipFile as e:
        logging.error(f"Failed to extract ZIP file: {e}")
        raise


def find_build_tools(sdk_root: Path, android_version: str) -> Optional[Path]:
    """Find the build-tools directory for the given version."""
    # First, try the exact version provided
    build_tools_dir = sdk_root / "build-tools" / android_version
    if build_tools_dir.exists():
        return build_tools_dir

    # Fallback: try major.minor.0 or major.0.0 format
    try:
        parts = android_version.split('.')
        if len(parts) >= 1:
            major = parts[0]
            # Try major.0.0
            fallback_dir1 = sdk_root / "build-tools" / f"{major}.0.0"
            if fallback_dir1.exists():
                return fallback_dir1
            # Try major.minor.0 if minor exists
            if len(parts) >= 2:
                minor = parts[1]
                fallback_dir2 = sdk_root / "build-tools" / f"{major}.{minor}.0"
                if fallback_dir2.exists():
                    return fallback_dir2
    except Exception as e:
        logging.warning(f"Error during build-tools fallback search: {e}")

    logging.error(
        f"Build tools directory not found for version {android_version} in {sdk_root}")
    return None


def get_sdk_tool_paths(sdk_root: Path, android_version: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Get paths to zipalign and apksigner.bat within the installed SDK.

    Returns:
        Tuple of (zipalign_path, apksigner_bat_path) or (None, None) if not found.
    """
    build_tools_dir = find_build_tools(sdk_root, android_version)
    if not build_tools_dir:
        return None, None

    # Find zipalign
    zipalign_path = build_tools_dir / config.ZIPALIGN_BIN
    # Check for .exe on Windows
    if not zipalign_path.exists() and platform.system().lower() == "windows":
        zipalign_path = build_tools_dir / f"{config.ZIPALIGN_BIN}.exe"

    # Find apksigner.bat
    apksigner_bat_path = build_tools_dir / config.APKSIGNER_BAT
    if not apksigner_bat_path.exists():
        logging.warning(f"apksigner.bat not found in {build_tools_dir}")
        apksigner_bat_path = None

    # Validation
    if not zipalign_path.exists():
        logging.warning(f"zipalign not found in {build_tools_dir}")
        zipalign_path = None
    if not apksigner_bat_path or not apksigner_bat_path.exists():
        logging.warning(f"apksigner.bat not found in {build_tools_dir}")
        apksigner_bat_path = None

    return zipalign_path, apksigner_bat_path


def run_command(cmd: list, cwd: Optional[str] = None, max_retries: int = 2) -> subprocess.CompletedProcess:
    """Run a shell command and return the result, with retry logic for common Windows file lock issues."""
    logging.info(f"Running command: {' '.join(cmd)}")
    for attempt in range(max_retries + 1):
        try:
            process = subprocess.run(
                cmd,
                cwd=cwd,
                text=True,
                capture_output=True,
                check=True
            )
            logging.debug(f"Command output: {process.stdout}")
            return process
        except subprocess.CalledProcessError as e:
            error_message = e.stderr
            logging.error(f"Command failed with return code {e.returncode}")
            logging.error(f"Error output: {error_message}")
            # Check if the error is related to file locks on Windows
            if ("The process cannot access the file because it is being used by another process" in error_message) and platform.system().lower() == "windows":
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logging.warning(
                        f"File lock error detected. Retrying command in {wait_time} seconds (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    logging.error(
                        "File lock error persists after retries. Consider closing other programs or retrying the command.")
                    raise  # Re-raise the last error after retries are exhausted
            else:
                # If it's not a retryable error, or retries are exhausted, re-raise immediately
                raise


def install_sdk_tools(
    sdk_root: Path,
    android_version: str = config.LATEST_ANDROID_VERSION,
    keep_cmdline: bool = True
) -> bool:
    """
    Install Android SDK tools directly into the SDK structure.

    Args:
        sdk_root: Path to Android SDK root directory (will be resolved to absolute)
        android_version: Android API version to install build tools for (format: X.X.X)
        keep_cmdline: Whether to keep commandline tools for future use

    Returns:
        True if installation successful, False otherwise
    """
    try:
        # Ensure sdk_root is absolute
        sdk_root = sdk_root.resolve()
        # Create SDK root directory
        sdk_root.mkdir(parents=True, exist_ok=True)
        logging.info(f"Using SDK root: {sdk_root}")

        # Create directory for commandline tools
        cmdline_dir = sdk_root / "cmdline-tools"
        cmdline_dir.mkdir(exist_ok=True)

        # Check if we already have commandline tools
        cmdline_latest = cmdline_dir / "latest"
        if not cmdline_latest.exists():
            # Download commandline tools
            platform_suffix = get_platform_suffix()
            download_url = config.COMMANDLINE_TOOLS_URL.format(platform_suffix)

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                zip_file = temp_path / "commandlinetools.zip"

                # Download and extract commandline tools
                download_file(download_url, zip_file)
                extract_zip(zip_file, temp_path)

                # Move to correct location
                # The zip contains a 'cmdline-tools' directory
                extracted_cmdline = temp_path / "cmdline-tools"
                if extracted_cmdline.exists():
                    shutil.move(str(extracted_cmdline), str(cmdline_latest))
                else:
                    # Sometimes it's extracted directly
                    shutil.move(str(temp_path / "bin"),
                                str(cmdline_latest / "bin"))
                    shutil.move(str(temp_path / "lib"),
                                str(cmdline_latest / "lib"))
        else:
            logging.info("Commandline tools already exist, skipping download")

        # Set up environment for sdkmanager
        cmdline_bin = cmdline_latest / "bin"

        # Accept licenses
        logging.info("Accepting SDK licenses...")
        accept_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "--licenses"
        ]

        try:
            # Use run_command which checks for success
            # Note: --licenses might require interaction, but sdkmanager sometimes accepts stdin
            process = subprocess.Popen(
                accept_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(
                input="y\n" * 20)  # Send multiple 'y' responses
            if process.returncode != 0:
                logging.warning(
                    f"License acceptance command finished with code {process.returncode}: {stderr}")
                logging.info(
                    "You might need to run 'sdkmanager --licenses' manually in the SDK directory.")
            else:
                logging.info("License acceptance command completed.")
        except Exception as e:
            logging.warning(
                f"Could not automatically accept licenses via command: {e}. You might need to run 'sdkmanager --licenses' manually in the SDK directory.")

        # Install build tools with retry logic for potential file locks
        logging.info(
            f"Installing build tools for Android API {android_version}...")

        # Extract major version for sdkmanager (e.g., 34.0.0 -> 34)
        major_version = android_version.split('.')[0]
        install_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            f"build-tools;{major_version}.0.0"
        ]
        # Use the enhanced run_command with retries
        run_command(install_cmd, cwd=str(sdk_root))

        # Install platform tools (adb, etc.) with retry logic
        logging.info("Installing platform tools...")
        platform_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system()
                == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "platform-tools"
        ]
        # Use the enhanced run_command with retries
        run_command(platform_cmd, cwd=str(sdk_root))

        # Verify tools are installed by trying to locate them
        zipalign_path, apksigner_bat_path = get_sdk_tool_paths(
            sdk_root, android_version)
        if zipalign_path and apksigner_bat_path:  # Check core tools
            logging.info(f"Found zipalign at: {zipalign_path}")
            logging.info(f"Found apksigner.bat at: {apksigner_bat_path}")
        else:
            logging.warning(
                "Could not locate core tools (zipalign or apksigner.bat) after installation. They might still be installed correctly.")

        logging.info("SDK tools installation process completed.")
        return True

    except subprocess.CalledProcessError as e:
        # Specific handling for command failures
        logging.error(
            f"SDK tools installation failed due to a command error: {e}")
        return False
    except Exception as e:
        logging.error(f"SDK tools installation failed: {e}")
        return False


def ensure_tools_available(tools_dir: Optional[Path], download_tools: bool = False,
                           sdk_root: Optional[Path] = None, android_version: Optional[str] = None) -> bool:
    """
    Ensure all required tools are available.
    Prioritizes tools_dir for apktool.jar, uses SDK for others.
    Installs SDK if download_tools is True.
    """
    # Ensure tools_dir exists if provided (caller should have checked this unless downloading)
    if tools_dir:
        tools_dir.mkdir(parents=True, exist_ok=True)

    # Check for apktool (must be in tools_dir if tools_dir is provided and not downloading)
    apktool_path = None
    if tools_dir:
        apktool_path = tools_dir / config.APKTOOL_JAR

    missing_tools = []
    if tools_dir and not apktool_path.exists():
        missing_tools.append("apktool")

    # Try to find or install SDK tools
    sdk_root_path = sdk_root if sdk_root else config.DEFAULT_SDK_ROOT
    target_android_version = android_version or config.DEFAULT_ANDROID_VERSION

    # If download is requested, install SDK tools first
    if download_tools:
        if not sdk_root_path:
            logging.error("SDK root path is required for downloading tools.")
            return False
        logging.info("Attempting to download/install Android SDK tools...")
        # Ensure sdk_root_path is absolute
        sdk_root_path = sdk_root_path.resolve()
        success = install_sdk_tools(
            sdk_root=sdk_root_path,
            android_version=target_android_version,
            # No tools_dir argument anymore for copying
            keep_cmdline=True
        )
        if not success:
            logging.error("Failed to install Android SDK tools via installer.")
            # Don't return False yet, check if tools might already exist

    # Try to locate tools within the SDK
    zipalign_path = None
    apksigner_path = None
    if sdk_root_path and sdk_root_path.exists():
        logging.info(
            f"Searching for SDK tools in {sdk_root_path} for version {target_android_version}...")
        # Ensure sdk_root_path is absolute for get_sdk_tool_paths
        sdk_root_path = sdk_root_path.resolve()
        zipalign_path, apksigner_path = get_sdk_tool_paths(
            sdk_root_path, target_android_version)

    # If not found via SDK, check in the tools_dir (fallback for manual placement)
    if not zipalign_path or not zipalign_path.exists():
        potential_zipalign = tools_dir / config.ZIPALIGN_BIN if tools_dir else None
        if potential_zipalign and potential_zipalign.exists():
            zipalign_path = potential_zipalign
            logging.info(f"Found zipalign in tools directory: {zipalign_path}")

    if not apksigner_path or not apksigner_path.exists():
        potential_apksigner = tools_dir / config.APKSIGNER_BAT if tools_dir else None
        if potential_apksigner and potential_apksigner.exists():
            apksigner_path = potential_apksigner
            logging.info(
                f"Found apksigner.jar in tools directory: {apksigner_path}")

    # Check for missing SDK tools
    if not zipalign_path or not zipalign_path.exists():
        missing_tools.append("zipalign")
    if not apksigner_path or not apksigner_path.exists():
        missing_tools.append("apksigner")

    if not missing_tools:
        logging.info("All required tools are available")
        return True

    if not download_tools:
        logging.error(f"Missing tools: {', '.join(missing_tools)}. "
                      "Please download them manually or use --download-tools option.")
        return False

    logging.info(f"Downloading missing tools: {', '.join(missing_tools)}")

    # Download apktool if missing and tools_dir is available
    if "apktool" in missing_tools and tools_dir:
        if not download_file(config.APKTOOL_DOWNLOAD_URL, apktool_path):
            logging.error("Failed to download apktool")
            return False

    # If we still couldn't find SDK tools after installation attempt and manual check, error
    still_missing = []
    if ("zipalign" in missing_tools or not (zipalign_path and zipalign_path.exists())):
        still_missing.append("zipalign")
    if ("apksigner" in missing_tools or not (apksigner_path and apksigner_path.exists())):
        still_missing.append("apksigner")

    if still_missing:
        logging.error(f"Failed to locate/download tools: {', '.join(still_missing)} "
                      f"even after SDK installation attempt. Check SDK root and Android version.")
        return False

    logging.info("All tools successfully installed/located")
    return True


def main():
    parser = argparse.ArgumentParser(description="Android SDK Tools Installer")
    parser.add_argument("--sdk-root", "-s", default=str(config.DEFAULT_SDK_ROOT),
                        help=f"Android SDK root directory (default: {config.DEFAULT_SDK_ROOT})")
    parser.add_argument("--android-version", "-V", default=config.LATEST_ANDROID_VERSION,
                        help=f"Android API version for build tools (default: {config.LATEST_ANDROID_VERSION})")
    # --tools-dir argument removed as tools are used in place
    parser.add_argument("--no-keep-cmdline", "-n", action="store_true",
                        help="Keep commandline tools after installation (default: True)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Convert paths
    sdk_root = Path(args.sdk_root).resolve()
    # tools_dir removed

    # Validate Android version
    try:
        version_parts = args.android_version.split('.')
        if len(version_parts) != 3:
            logging.warning(
                f"Android version {args.android_version} should be in X.X.X format")
        version_int = int(version_parts[0])
        if version_int < int(config.MIN_ANDROID_VERSION.split('.')[0]) or version_int > int(config.LATEST_ANDROID_VERSION.split('.')[0]) + 5:
            logging.warning(f"Android version {args.android_version} might be invalid. "
                            f"Supported range: {config.MIN_ANDROID_VERSION}-{int(config.LATEST_ANDROID_VERSION.split('.')[0]) + 5}.0.0")
    except ValueError:
        logging.warning(f"Invalid Android version: {args.android_version}")

    # Install tools
    success = install_sdk_tools(
        sdk_root=sdk_root,
        android_version=args.android_version,
        keep_cmdline=not args.no_keep_cmdline
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
