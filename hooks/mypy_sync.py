#!/usr/bin/env python

import importlib.metadata
import shutil
import sys
import tempfile
from typing import IO
from typing import Iterator

import yaml

package_versions = {
    dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()
}


class UpdateDependencies:
    def __init__(self, fn: str, new_deps: list[str]):
        self.fn = fn
        self.new_deps = new_deps
        self.state = "pre"
        self.indent = ""

    def handle(self, line: str) -> Iterator[str]:
        match self.state:
            case "pre":
                yield line
                if line.strip() == "additional_dependencies:":
                    self.state = "in-deps"
                    self.indent = " " * sum(1 for c in line.rstrip() if c == " ")

            case "in-deps":
                for dep in self.new_deps:
                    yield f'{self.indent}  - "{dep}"\n'

                self.state = "skip-old-deps"

            case "skip-old-deps":
                if not line.startswith(f"{self.indent}  -"):
                    yield line
                    self.state = "post"

            case "post":
                yield line

    def __iter__(self) -> Iterator[str]:
        with open(self.fn) as fp:
            for line in fp:
                yield from self.handle(line)


def do(outfp: IO[str]) -> None:
    with open(".pre-commit-config.yaml") as fp:
        cfg = yaml.safe_load(fp)

    mypy = [
        tool
        for tool in cfg["repos"]
        if tool["repo"] == "https://github.com/pre-commit/mirrors-mypy"
    ][0]
    dependencies = mypy["hooks"][0]["additional_dependencies"]

    new_deps = []
    for dep in dependencies:
        name = dep.split("=", 1)[0]
        if name in package_versions:
            new_deps.append(f"{name}=={package_versions[name]}")
        else:
            new_deps.append(dep)

    outfp.writelines(UpdateDependencies(".pre-commit-config.yaml", new_deps))


def main() -> None:
    if sys.argv[-1] == "--in-place":
        with tempfile.NamedTemporaryFile(mode="w") as ofp:
            do(ofp)
            ofp.flush()
            shutil.copy(ofp.file.name, ".pre-commit-config.yaml")
    else:
        do(sys.stdout)

    
if __name__ == "__main__":
    main()
