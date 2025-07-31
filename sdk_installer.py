import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

# Constants
DEFAULT_ANDROID_SDK_ROOT = Path.home() / "android-sdk"
DEFAULT_TOOLS_DIR = "./tools"
COMMANDLINE_TOOLS_URL = "https://dl.google.com/android/repository/commandlinetools-{}-9477386_latest.zip"
LATEST_ANDROID_VERSION = "34"  # Android 14 (API 34)
MIN_ANDROID_VERSION = "21"     # Android 5.0 (API 21)

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

def run_command(cmd: list, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    logging.info(f"Running command: {' '.join(cmd)}")
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
        logging.error(f"Command failed with return code {e.returncode}")
        logging.error(f"Error output: {e.stderr}")
        raise

def install_sdk_tools(
    sdk_root: Path,
    android_version: str = LATEST_ANDROID_VERSION,
    tools_dir: Optional[Path] = None,
    keep_cmdline: bool = True
) -> bool:
    """
    Install Android SDK tools
    
    Args:
        sdk_root: Path to Android SDK root directory
        android_version: Android API version to install build tools for
        tools_dir: Directory to copy final tools to (optional)
        keep_cmdline: Whether to keep commandline tools for future use
    
    Returns:
        True if installation successful, False otherwise
    """
    try:
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
            download_url = COMMANDLINE_TOOLS_URL.format(platform_suffix)
            
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
                    shutil.move(str(temp_path / "bin"), str(cmdline_latest / "bin"))
                    shutil.move(str(temp_path / "lib"), str(cmdline_latest / "lib"))
        else:
            logging.info("Commandline tools already exist, skipping download")
        
        # Set up environment for sdkmanager
        cmdline_bin = cmdline_latest / "bin"
        env = os.environ.copy()
        
        # Add commandline tools to PATH
        current_path = env.get("PATH", "")
        env["PATH"] = f"{cmdline_bin}{os.pathsep}{current_path}"
        
        # Accept licenses
        logging.info("Accepting SDK licenses...")
        accept_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system() == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "--licenses"
        ]
        
        try:
            process = subprocess.Popen(
                accept_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            stdout, stderr = process.communicate(input="y\n" * 10)  # Accept all licenses
            if process.returncode != 0:
                logging.warning(f"License acceptance had issues: {stderr}")
        except Exception as e:
            logging.warning(f"Could not automatically accept licenses: {e}")
        
        # Install build tools
        logging.info(f"Installing build tools for Android API {android_version}...")
        install_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system() == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            f"build-tools;{android_version}.0"
        ]
        
        run_command(install_cmd, cwd=str(sdk_root))
        
        # Install platform tools (adb, etc.)
        logging.info("Installing platform tools...")
        platform_cmd = [
            str(cmdline_bin / ("sdkmanager.bat" if platform.system() == "Windows" else "sdkmanager")),
            "--sdk_root=" + str(sdk_root),
            "platform-tools"
        ]
        
        run_command(platform_cmd, cwd=str(sdk_root))
        
        # Copy required tools to tools_dir if specified
        if tools_dir:
            tools_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Copying tools to {tools_dir}")
            
            # Copy build tools
            build_tools_dir = sdk_root / "build-tools" / f"{android_version}.0"
            if build_tools_dir.exists():
                zipalign_src = build_tools_dir / "zipalign"
                if zipalign_src.exists():
                    shutil.copy2(zipalign_src, tools_dir / "zipalign")
                    # Make executable on Unix-like systems
                    if platform.system() != "Windows":
                        os.chmod(tools_dir / "zipalign", 0o755)
                
                # Look for apksigner.jar
                for file in build_tools_dir.glob("*.jar"):
                    if "apksigner" in file.name.lower():
                        shutil.copy2(file, tools_dir / "apksigner.jar")
            
            # Copy platform tools if needed
            platform_tools_dir = sdk_root / "platform-tools"
            if platform_tools_dir.exists():
                # ADB might be needed for some operations
                pass  # We're focusing on apktool, apksigner, and zipalign
            
            # Note: apktool needs to be downloaded separately as it's not part of Android SDK
            logging.info("Note: apktool.jar needs to be downloaded separately and placed in the tools directory")
        
        logging.info("SDK tools installation completed successfully")
        return True
        
    except Exception as e:
        logging.error(f"SDK tools installation failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Android SDK Tools Installer")
    parser.add_argument("--sdk-root", default=DEFAULT_ANDROID_SDK_ROOT, 
                       help=f"Android SDK root directory (default: {DEFAULT_ANDROID_SDK_ROOT})")
    parser.add_argument("--android-version", default=LATEST_ANDROID_VERSION,
                       help=f"Android API version for build tools (default: {LATEST_ANDROID_VERSION})")
    parser.add_argument("--tools-dir", 
                       help="Directory to copy final tools to (optional)")
    parser.add_argument("--no-keep-cmdline", action="store_true",
                       help="Delete commandline tools after installation")
    parser.add_argument("--verbose", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Convert paths
    sdk_root = Path(args.sdk_root).resolve()
    tools_dir = Path(args.tools_dir).resolve() if args.tools_dir else None
    
    # Validate Android version
    try:
        version_int = int(args.android_version)
        if version_int < int(MIN_ANDROID_VERSION) or version_int > int(LATEST_ANDROID_VERSION) + 5:
            logging.warning(f"Android version {args.android_version} might be invalid. "
                          f"Supported range: {MIN_ANDROID_VERSION}-{int(LATEST_ANDROID_VERSION) + 5}")
    except ValueError:
        logging.warning(f"Invalid Android version: {args.android_version}")
    
    # Install tools
    success = install_sdk_tools(
        sdk_root=sdk_root,
        android_version=args.android_version,
        tools_dir=tools_dir,
        keep_cmdline=not args.no_keep_cmdline
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
