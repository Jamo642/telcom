"""
Quick deployment check script
Verifies all services are running and accessible
"""

import subprocess
import requests
import time
import sys

def run_command(cmd):
    """Run shell command"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def check_docker():
    """Check if Docker is running"""
    success, output = run_command("docker ps")
    return success

def check_containers():
    """Check if all required containers are running"""
    success, output = run_command("docker-compose -f docker/docker-compose.yml ps")
    if success:
        return "ollama" in output and "backend" in output and "frontend" in output
    return False

def check_backend_health():
    """Check backend health"""
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def check_streamlit():
    """Check if Streamlit is accessible"""
    try:
        response = requests.get("http://localhost:8501", timeout=5)
        return response.status_code in [200, 401]  # 401 if auth, 200 if accessible
    except:
        return False

def check_database():
    """Check if database is initialized"""
    try:
        response = requests.get("http://localhost:8000/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            doc_count = stats.get("collection", {}).get("document_count", 0)
            return doc_count > 0
    except:
        pass
    return False

def main():
    print("🔍 Deployment Health Check")
    print("=" * 50)
    print()
    
    checks = [
        ("Docker", check_docker),
        ("Docker Containers", check_containers),
        ("Backend Health", check_backend_health),
        ("Streamlit UI", check_streamlit),
        ("Database Initialized", check_database),
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        try:
            passed = check_func()
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {check_name}")
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"❌ FAIL - {check_name}: {e}")
            all_passed = False
    
    print()
    print("=" * 50)
    
    if all_passed:
        print("✅ All checks passed! System is ready.")
        print()
        print("🌐 Access:")
        print("   Frontend: http://localhost:8501")
        print("   Backend:  http://localhost:8000")
        print("   API Docs: http://localhost:8000/docs")
        return 0
    else:
        print("❌ Some checks failed. Troubleshooting:")
        print()
        print("1. Check Docker: docker ps")
        print("2. Check logs: docker-compose -f docker/docker-compose.yml logs")
        print("3. Start services: docker-compose -f docker/docker-compose.yml up")
        print("4. Initialize DB: curl -X POST http://localhost:8000/initialize")
        return 1

if __name__ == "__main__":
    sys.exit(main())
