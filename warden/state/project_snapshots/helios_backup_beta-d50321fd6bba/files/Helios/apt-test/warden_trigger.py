import subprocess
def run():
    subprocess.check_call(['whoami'], shell=True)  # still violates shell=False guard
