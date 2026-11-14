#!/usr/bin/env bash
# Runs the workflow step's own script (cut from a step file) over local cases.
# Usage: step-test.sh <step file> <path to a .gitleaks.toml> <empty work dir>
# Extends ryanduguid-evaluation-fixes-2026-11-13's step-test.sh (cases a to h)
# with R2642's cases i to r: whose .gitleaks.toml, .gitleaksignore, inline
# allow comments and .gitattributes the scan honours. Every identifier is
# fabricated: the ABN
# 98 765 432 100 fails the ABN checksum and no repository's config allowlists
# it (12 345 678 901, used before, is allowlisted in australian-accounting).
set -euo pipefail
step=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
config=$2
work=$3
rm -rf "$work"
mkdir -p "$work"
cd "$work"
# The step's script: every line after `run: |`, less its 10 spaces of indent.
sed -n '/^        run: |$/,$p' "$step" | sed '1d; s/^          //' > ../step-run.sh

git init -q -b main .
git config user.name t
git config user.email t@example.invalid
git config commit.gpgsign false
git config advice.detachedHead false
git config core.autocrlf false
cp "$config" .gitleaks.toml
printf 'line 1\nline 2\nline 3\n' > notes.txt
printf 'top\nmid\nbottom\n' > h1.txt
git add -A
git commit -q -m base
base=$(git rev-parse HEAD)

# The fabricated values, held apart from their labels so that this file
# itself holds nothing a rule matches.
bizid='98 765 432 100'
taxid='123 456 782'
atoid='51 824 753 556'

commit_file() { # <file> <content> <message>
  printf '%s\n' "$2" > "$1"
  git add -A
  git commit -q -m "$3"
}

# (a) a commit holding a fabricated ABN reaches the branch through a merge.
git checkout -q -b side
commit_file supplier.txt "Supplier ABN: $bizid" 'side: supplier'
git checkout -q -b pr-a "$base"
commit_file pr.txt 'pr work' 'pr: work'
git merge -q --no-ff -m 'merge side' side
head_a=$(git rev-parse HEAD)

# (b) both sides edit line 2 and the merge's resolution adds a TFN.
git checkout -q -b other "$base"
printf 'line 1\nline 2 other\nline 3\n' > notes.txt
git commit -q -am 'other: edit'
git checkout -q -b pr-b "$base"
printf 'line 1\nline 2 pr\nline 3\n' > notes.txt
git commit -q -am 'pr-b: edit'
git merge -q --no-ff other > /dev/null 2>&1 || true
printf 'line 1\nline 2 both, TFN %s\nline 3\n' "$taxid" > notes.txt
git commit -q -am 'merge other (resolved)'
head_b=$(git rev-parse HEAD)

# (c) a clean merge of main, which holds an allowlisted line, into the branch.
git checkout -q main
commit_file ato.txt "ATO ABN: $atoid" 'main: ato example'
git checkout -q -b pr-c "$base"
commit_file c.txt 'c' 'pr-c: work'
git merge -q --no-ff -m 'merge main' main
head_c=$(git rev-parse HEAD)

# (d) 31 commits; the 31st holds the ABN.
git checkout -q -b pr-d "$base"
for n in $(seq 1 30); do commit_file "d$n.txt" "d $n" "pr-d: $n"; done
commit_file d31.txt "Supplier ABN: $bizid" 'pr-d: 31'
head_d=$(git rev-parse HEAD)

# (e) a merge of three parents that itself adds the ABN.
git checkout -q -b e1 "$base"
commit_file e1.txt 'e1' 'e1'
git checkout -q -b e2 "$base"
commit_file e2.txt 'e2' 'e2'
git checkout -q -b pr-e "$base"
commit_file e.txt 'e' 'pr-e: work'
git merge -q --no-ff --no-commit e1 e2
printf 'Supplier ABN: %s\n' "$bizid" > octopus.txt
git add -A
git commit -q -m 'merge e1 and e2, adding a file'
head_e=$(git rev-parse HEAD)

# (h) the branch adds the ABN in a commit; a later conflict on the same line is
# resolved by keeping that line unchanged.
git checkout -q -b other-h "$base"
printf 'top\nmid other\nbottom\n' > h1.txt
git commit -q -am 'other-h: edit'
git checkout -q -b pr-h "$base"
printf 'top\nSupplier ABN: %s\nbottom\n' "$bizid" > h1.txt
git commit -q -am 'pr-h: supplier'
commit_h=$(git rev-parse HEAD)
git merge -q --no-ff other-h > /dev/null 2>&1 || true
printf 'top\nSupplier ABN: %s\nbottom\n' "$bizid" > h1.txt
git commit -q -am 'merge other-h (kept ours)'
head_h=$(git rev-parse HEAD)

# R2642 cases. The base (main's first commit) has no .gitleaksignore.
# (i) the pull request adds the ABN and allowlists its file in .gitleaks.toml.
git checkout -q -b pr-i "$base"
printf 'Supplier ABN: %s\n' "$bizid" > pr-i.txt
cat >> .gitleaks.toml <<'EOF'

[[allowlists]]
description = "Added by the pull request"
paths = ['''^pr-i\.txt$''']
EOF
git add -A
git commit -q -m 'pr-i: supplier, allowlisted in .gitleaks.toml'
head_i=$(git rev-parse HEAD)

# (j) the pull request adds the ABN, then its fingerprint in .gitleaksignore.
git checkout -q -b pr-j "$base"
commit_file pr-j.txt "Supplier ABN: $bizid" 'pr-j: supplier'
commit_j=$(git rev-parse HEAD)
commit_file .gitleaksignore "$commit_j:pr-j.txt:au-business-number:1" 'pr-j: ignore it'
head_j=$(git rev-parse HEAD)

# (k) the pull request adds the ABN with an inline gitleaks:allow comment.
git checkout -q -b pr-k "$base"
commit_file pr-k.txt "Supplier ABN: $bizid # gitleaks:allow" 'pr-k: supplier, inline allow'
head_k=$(git rev-parse HEAD)

# (l) a base without .gitleaksignore and a clean pull request.
git checkout -q -b pr-l "$base"
commit_file pr-l.txt 'nothing to find' 'pr-l: work'
head_l=$(git rev-parse HEAD)

# (m) the pull request adds the ABN; its fingerprint reached the base first, in
# its own commit, and the branch then merged the base.
git checkout -q -b pr-m "$base"
commit_file pr-m.txt "Supplier ABN: $bizid" 'pr-m: supplier'
commit_m=$(git rev-parse HEAD)
git checkout -q -b base-m "$base"
commit_file .gitleaksignore "$commit_m:pr-m.txt:au-business-number:1" 'base-m: ignore pr-m'
base_m=$(git rev-parse HEAD)
git checkout -q pr-m
git merge -q --no-ff -m 'merge base-m' base-m
head_m=$(git rev-parse HEAD)

# (n) a base without .gitleaks.toml; the pull request adds one that allowlists
# the ABN it also adds.
git checkout -q --orphan base-n
git rm -q -r --cached . > /dev/null
git clean -q -fdx
commit_file readme.txt 'no config here' 'base-n: no gitleaks config'
base_n=$(git rev-parse HEAD)
git checkout -q -b pr-n
cp "$config" .gitleaks.toml
printf '\n[[allowlists]]\npaths = ['"'''"'^pr-n\\.txt$'"'''"']\n' >> .gitleaks.toml
printf 'Supplier ABN: %s\n' "$bizid" > pr-n.txt
git add -A
git commit -q -m 'pr-n: config and supplier'
head_n=$(git rev-parse HEAD)

# (o) the pull request edits .gitleaks.toml and adds nothing to find.
git checkout -q -b pr-o "$base"
printf '\n# A comment the pull request adds.\n' >> .gitleaks.toml
commit_file pr-o.txt 'nothing to find' 'pr-o: comment in the config'
head_o=$(git rev-parse HEAD)

# (p) an allowlist already in the base's .gitleaks.toml covers the ABN the pull
# request adds.
git checkout -q -b base-p "$base"
cat >> .gitleaks.toml <<'EOF'

[[allowlists]]
description = "Reviewed on the base"
paths = ['''^pr-p\.txt$''']
EOF
git add -A
git commit -q -m 'base-p: allowlist pr-p.txt'
base_p=$(git rev-parse HEAD)
git checkout -q -b pr-p
commit_file pr-p.txt "Supplier ABN: $bizid" 'pr-p: supplier'
head_p=$(git rev-parse HEAD)

# (q) the pull request adds a .gitattributes that marks every file -diff, so a
# git log run in its checkout shows no text, and the ABN.
git checkout -q -b pr-q "$base"
printf '%s\n' '* -diff' > .gitattributes
commit_file pr-q.txt "Supplier ABN: $bizid" 'pr-q: supplier, diff turned off'
head_q=$(git rev-parse HEAD)

# Like actions/checkout, run each case with the pull request's files in the
# working tree, so a step that reads ./.gitleaks.toml or ./.gitleaksignore
# reads the pull request's copies.
# <expect> is leak (fails with a finding), fail (fails), pass or any. With
# EXPECT=1 in the environment a case that does not match is a MISMATCH and the
# harness exits 1; leave it unset for the old step.
# (r) puts this git first on PATH: it fails any git log run under the step's
# RUNNER_TEMP, as a git failure confined to the scan's folder would.
fakebin="$(cd .. && pwd)/fakebin"
mkdir -p "$fakebin"
real_git=$(command -v git)
cat > "$fakebin/git" <<EOF
#!/usr/bin/env bash
case "\$PWD" in
  "\$RUNNER_TEMP"/*) for a in "\$@"; do [ "\$a" = log ] && { echo 'injected: git log failed' >&2; exit 1; }; done ;;
esac
exec "$real_git" "\$@"
EOF
chmod +x "$fakebin/git"
mismatches=0
run() { # <label> <base> <head> <expect> [path prefix]
  local code tmp findings verdict=''
  git checkout -q -f --detach "$3" 2> /dev/null || true
  tmp=$(mktemp -d)
  set +e
  PATH="${5:+$5:}$PATH" BASE_SHA=$2 HEAD_SHA=$3 RUNNER_TEMP=$tmp bash -e ../step-run.sh > "../out-$1.txt" 2>&1
  code=$?
  set -e
  rm -rf "$tmp"
  findings=$(grep -c '^RuleID' "../out-$1.txt" || true)
  if [ "${EXPECT:-}" = 1 ]; then
    case "$4" in
      leak) [ "$code" -ne 0 ] && [ "$findings" -gt 0 ] ;;
      fail) [ "$code" -ne 0 ] ;;
      pass) [ "$code" -eq 0 ] ;;
      any) true ;;
    esac && verdict="ok($4)" || { verdict="MISMATCH(expected $4)"; mismatches=$((mismatches + 1)); }
  fi
  printf '%-34s exit=%s findings=%s %s commits=[%s] %s\n' "$1" "$code" "$findings" "$verdict" \
    "$(grep '^Commit' "../out-$1.txt" | awk '{print substr($2,1,7)}' | tr '\n' ' ' || true)" \
    "$(sed 's/\x1b\[[0-9;]*m//g' "../out-$1.txt" | grep -E '^::error::|scanned|fatal' | cut -c1-150 | tr '\n' '|' || true)"
}

echo "git $(git --version | awk '{print $3}'), gitleaks $(gitleaks version)"
echo "side $(git rev-parse --short side), merge b $(git rev-parse --short pr-b), 31st $(git rev-parse --short pr-d), octopus $(git rev-parse --short pr-e), pr-h commit ${commit_h:0:7}, pr-h merge ${head_h:0:7}"
echo "pr-i ${head_i:0:7}, pr-j commit ${commit_j:0:7}, pr-k ${head_k:0:7}, pr-m commit ${commit_m:0:7}, pr-n ${head_n:0:7}"
run a-merged-in-commit "$base" "$head_a" leak
run b-merge-resolution "$base" "$head_b" leak
# With the base main had when the branch was cut, main's own commit is in range;
# with main's tip as the base, only the branch's commits and the merge are.
run c-clean-merge-stale-base "$base" "$head_c" any
run c-clean-merge-fresh-base "$(git rev-parse main)" "$head_c" pass
run d-31-commits "$base" "$head_d" leak
run e-three-parent-merge "$base" "$head_e" fail
run f-same-sha "$head_a" "$head_a" fail
run f-head-behind-base "$head_a" "$base" fail
run g-unknown-base 0123456789012345678901234567890123456789 "$head_a" fail
run g-empty-sha '' "$head_a" fail
run h-kept-line-no-ignore "$base" "$head_h" leak
# The fingerprint sits only in the pull request's working tree, as if the pull
# request had added it.
git checkout -q -f --detach "$head_h"
printf '%s:h1.txt:au-business-number:2\n' "$commit_h" > .gitleaksignore
run h-kept-line-fingerprint-ignored "$base" "$head_h" leak
rm .gitleaksignore
run i-pr-toml-allowlists-its-abn "$base" "$head_i" leak
run j-pr-ignore-fingerprints-abn "$base" "$head_j" leak
run k-pr-inline-gitleaks-allow "$base" "$head_k" leak
run l-base-no-ignore-clean-pr "$base" "$head_l" pass
run m-base-ignore-fingerprints-pr "$base_m" "$head_m" pass
run n-base-no-toml "$base_n" "$head_n" fail
run o-pr-edits-toml-clean "$base" "$head_o" pass
run p-base-toml-allowlists-pr "$base_p" "$head_p" pass
run q-pr-gitattributes-no-diff "$base" "$head_q" leak
run r-injected-scan-git-failure "$base" "$head_l" fail "$fakebin"
if [ "${EXPECT:-}" = 1 ]; then
  echo "mismatches=$mismatches"
  [ "$mismatches" -eq 0 ]
fi
