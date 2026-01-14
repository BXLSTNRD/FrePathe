import subprocess
import sys

def get_git_log():
    try:
        result = subprocess.run(
            ["git", "log", "--oneline"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            print("Error fetching git log:", result.stderr)
            sys.exit(1)
        return result.stdout.splitlines()
    except Exception as e:
        print("Error running git log:", e)
        sys.exit(1)

def validate_changelog():
    try:
        with open("CHANGELOG.md", "r") as changelog_file:
            changelog_content = changelog_file.read()

        git_log = get_git_log()
        missing_entries = []

        for log_entry in git_log:
            commit_hash, *message = log_entry.split(" ", 1)
            if commit_hash not in changelog_content:
                missing_entries.append(log_entry)

        if missing_entries:
            print("The following commits are missing from the changelog:")
            for entry in missing_entries:
                print(entry)
            sys.exit(1)
        else:
            print("Changelog is up-to-date.")

    except FileNotFoundError:
        print("CHANGELOG.md not found. Please ensure it exists in the project root.")
        sys.exit(1)
    except Exception as e:
        print("Error validating changelog:", e)
        sys.exit(1)

if __name__ == "__main__":
    validate_changelog()