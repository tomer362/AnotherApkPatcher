# merger.py
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Constants
DEFAULT_APKEDITOR_JAR = "libs/APKEditor/APKEditor.jar"
DEFAULT_MERGED_APK_NAME = "merged_apk.apk"

def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)

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

def build_apkeditor() -> bool:
    """Build APKEditor from source"""
    try:
        apkeditor_dir = Path("libs/APKEditor")
        if not apkeditor_dir.exists():
            logging.error("APKEditor submodule not found. Please initialize submodules.")
            return False
        
        # Check if gradlew exists
        gradlew = apkeditor_dir / ("gradlew.bat" if sys.platform == "win32" else "gradlew")
        if not gradlew.exists():
            logging.error("Gradle wrapper not found in APKEditor directory")
            return False
        
        # Make gradlew executable on Unix-like systems
        if sys.platform != "win32":
            import stat
            current_permissions = gradlew.stat().st_mode
            gradlew.chmod(current_permissions | stat.S_IEXEC)
        
        # Build APKEditor
        logging.info("Building APKEditor...")
        build_cmd = [str(gradlew), "build"]
        if sys.platform == "win32":
            build_cmd = [str(gradlew), "build"]
        
        run_command(build_cmd, cwd=str(apkeditor_dir))
        
        # Find the built JAR
        jar_path = apkeditor_dir / "app" / "build" / "libs"
        if not jar_path.exists():
            logging.error("APKEditor build output directory not found")
            return False
            
        # Find the JAR file
        jar_files = list(jar_path.glob("*.jar"))
        if not jar_files:
            logging.error("No JAR file found in APKEditor build output")
            return False
            
        # Copy the JAR to the root for easier access
        target_jar = Path("libs/APKEditor/APKEditor.jar")
        target_jar.write_bytes(jar_files[0].read_bytes())
        
        logging.info("APKEditor built successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to build APKEditor: {e}")
        return False

def merge_apks(
    base_apk: str,
    unsigned_apk: str,
    output_apk: str,
    apkeditor_jar: str = DEFAULT_APKEDITOR_JAR,
    verbose: bool = False
) -> bool:
    """
    Merge two APKs using APKEditor's merge feature
    
    Args:
        base_apk: Path to the base APK
        unsigned_apk: Path to the unsigned APK to merge
        output_apk: Path for the output merged APK
        apkeditor_jar: Path to APKEditor JAR file
        verbose: Enable verbose logging
        
    Returns:
        True if merge successful, False otherwise
    """
    setup_logging(verbose)
    
    # Check if APKEditor JAR exists, if not try to build it
    jar_path = Path(apkeditor_jar)
    if not jar_path.exists():
        logging.warning(f"APKEditor JAR not found at {apkeditor_jar}")
        logging.info("Attempting to build APKEditor...")
        if not build_apkeditor():
            logging.error("Failed to build APKEditor")
            return False
        logging.info("APKEditor built successfully")
    
    # Verify input APKs exist
    base_apk_path = Path(base_apk)
    unsigned_apk_path = Path(unsigned_apk)
    
    if not base_apk_path.exists():
        logging.error(f"Base APK not found: {base_apk}")
        return False
    
    if not unsigned_apk_path.exists():
        logging.error(f"Unsigned APK not found: {unsigned_apk}")
        return False
    
    try:
        # Run APKEditor merge command
        # APKEditor.jar merge -i base.apk -u unsigned.apk -o output.apk
        merge_cmd = [
            "java", "-jar", str(jar_path),
            "merge",
            "-i", str(base_apk_path),
            "-u", str(unsigned_apk_path),
            "-o", str(output_apk)
        ]
        
        run_command(merge_cmd)
        logging.info(f"APKs merged successfully to {output_apk}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to merge APKs: {e}")
        return False

def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="APK Merger using APKEditor")
    parser.add_argument("base_apk", help="Path to the base APK")
    parser.add_argument("unsigned_apk", help="Path to the unsigned APK to merge")
    parser.add_argument("-o", "--output", default=DEFAULT_MERGED_APK_NAME,
                       help=f"Output APK path (default: {DEFAULT_MERGED_APK_NAME})")
    parser.add_argument("--apkeditor-jar", default=DEFAULT_APKEDITOR_JAR,
                       help=f"Path to APKEditor JAR (default: {DEFAULT_APKEDITOR_JAR})")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--build", action="store_true", 
                       help="Build APKEditor from source before merging")
    
    args = parser.parse_args()
    
    # Build APKEditor if requested
    if args.build:
        setup_logging(args.verbose)
        if not build_apkeditor():
            return 1
    
    # Perform merge
    success = merge_apks(
        base_apk=args.base_apk,
        unsigned_apk=args.unsigned_apk,
        output_apk=args.output,
        apkeditor_jar=args.apkeditor_jar,
        verbose=args.verbose
    )
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
