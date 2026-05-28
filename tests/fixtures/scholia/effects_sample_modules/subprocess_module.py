"""Sample module exercising the subprocess detector."""
import os
import subprocess


def run_git():
    subprocess.run(["git", "status"], check=True)


def shell_echo():
    os.system("echo hi")


def popen_ls():
    return os.popen("ls").read()
