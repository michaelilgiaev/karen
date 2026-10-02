<p align="center">
  <img src="assets/karen_title_627×230.png" alt="karen">
</p>

`karen` manages a git repository: `karen commit` commits the staged diff with a model-written subject, and `karen version` bumps semver and tags `vX.Y.Z` locally (the model picks the bump, or you pass `major`/`minor`/`patch`; push it with `git push origin master --tags`). Uses Anthropic API.

## Setup

Documentation only covers Arch-based systems.

Export Anthropic API key to `~/.bashrc`:

```bash
export ANTHROPIC_API="API_GOES_HERE"
```

Then install:

```
sudo pacman --sync --refresh --needed --noconfirm - < packages_x86_64 \
    && bash compile.sh \
    && sudo install -m 755 output/karen /usr/bin/ \
    && sudo install -m 644 libraries/completion.bash /usr/share/bash-completion/completions/karen
```
