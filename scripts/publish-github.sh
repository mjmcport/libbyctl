#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 OWNER/REPO [public|private]"
  exit 2
fi

REPO="$1"
VISIBILITY="${2:-public}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required. Install it from https://cli.github.com/ and run: gh auth login"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login"
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Run this script from the libbyctl repository root."
  exit 1
fi

case "$VISIBILITY" in
  public|private) ;;
  *) echo "Visibility must be public or private"; exit 2 ;;
esac

if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repository $REPO already exists."
else
  gh repo create "$REPO" --"$VISIBILITY" --description "Planner-first CLI for Libby/OverDrive across multiple library cards"
fi

URL="https://github.com/${REPO}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi

git branch -M main
git push -u origin main

echo "Published to https://github.com/${REPO}"
