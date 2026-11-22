.PHONY: build validate package clean

build:
	python3 build.py

validate:
	python3 build.py --check
	python3 validate.py

# `vsce package` is intentionally not executed here: it needs npm and network
# access. Run it manually from the repository root. Because package.json now
# carries the GitHub repository URL, no --baseContentUrl/--baseImagesUrl flags
# are required. Repository: https://github.com/42vibes/42vibes-vscode
package:
	@echo "Not executed on purpose: packaging needs vsce/npm (and possibly network)."
	@echo "Run: npx --yes @vscode/vsce package"

clean:
	rm -rf themes/__pycache__ __pycache__ *.vsix
