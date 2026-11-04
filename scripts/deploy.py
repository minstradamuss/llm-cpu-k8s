import argparse
import os
import runpy
import subprocess
from pathlib import Path


def run(*args):
    subprocess.run(args, check=True)


parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="vllm-cpu")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
os.chdir(root)
runpy.run_path(str(root / "scripts/create_secrets.py"), run_name="__main__")
run("minikube", "start", "-p", args.profile, "--driver=docker", "--cpus=6", "--memory=8192", "--kubernetes-version=v1.37.0")
run("docker", "build", "--platform=linux/amd64", "-t", "student-vllm-cpu:1.0", ".")
run("docker", "build", "--platform=linux/amd64", "-t", "student-model-init:1.0", "-f", "Dockerfile.init", ".")
run("minikube", "-p", args.profile, "image", "load", "student-vllm-cpu:1.0", "student-model-init:1.0")
run("kubectl", "--context", args.profile, "apply", "-k", "k8s/overlays/local")
run("kubectl", "--context", args.profile, "-n", "llm-cpu", "rollout", "status", "deployment/llm", "--timeout=1800s")
print("Ready. Run: kubectl --context " + args.profile + " -n llm-cpu port-forward service/llm 8000:8000")
