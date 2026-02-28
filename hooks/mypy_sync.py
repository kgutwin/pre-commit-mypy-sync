#!/usr/bin/env python

import argparse
import importlib.metadata
import re
import shutil
import subprocess
import sys
import tempfile
from typing import IO
from typing import Iterator

import yaml


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


def do(outfp: IO[str], package_versions: dict[str, str]) -> None:
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
            print(f"{name} not currently installed, skipping")
            new_deps.append(dep)

    outfp.writelines(UpdateDependencies(".pre-commit-config.yaml", new_deps))


def main() -> None:
    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="Change .pre-commit-config.yaml file in place",
    )
    argparser.add_argument(
        "--pip-install",
        "-p",
        action="append",
        metavar="SPEC",
        help="invoke `pip install SPEC`",
    )
    argparser.add_argument(
        "--requirements",
        "-r",
        action="append",
        metavar="FILE",
        help="pip install requirements from FILE",
    )
    argparser.add_argument(
        "--no-install",
        "-N",
        action="store_true",
        help="skip pip install, parse requirements file directly",
    )

    opts = argparser.parse_args()

    if not opts.no_install:
        pip_args = []
        for req in opts.requirements or []:
            pip_args.extend(["-r", req])

        for req in opts.pip_install or []:
            pip_args.append(req)

        if pip_args:
            args = [sys.executable, "-m", "pip", "install"] + pip_args
            subprocess.check_call(args)

        package_versions = {
            dist.metadata["Name"]: dist.version
            for dist in importlib.metadata.distributions()
        }

    elif opts.requirements:
        package_versions = {}
        for req in opts.requirements:
            for line in open(req):
                line = line.strip()
                if line.startswith("#") or line == "":
                    continue

                if m := re.match(r"^(\S+)\s*==\s*(\S+)$", line):
                    package_versions[m.group(1)] = m.group(2)
                else:
                    raise ValueError(f"unable to parse requirement: {line}")

    else:
        # use the current installed packages
        package_versions = {
            dist.metadata["Name"]: dist.version
            for dist in importlib.metadata.distributions()
        }

    if opts.in_place:
        with tempfile.NamedTemporaryFile(mode="w") as ofp:
            do(ofp, package_versions)
            ofp.flush()
            shutil.copy(ofp.file.name, ".pre-commit-config.yaml")
    else:
        do(sys.stdout, package_versions)


if __name__ == "__main__":
    main()
