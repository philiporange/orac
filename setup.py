from pathlib import Path
from setuptools import setup, find_packages

# Read project metadata from orac/__init__.py
about = {}
init_path = Path(__file__).parent / "orac" / "_meta.py"
with open(init_path, encoding="utf-8") as f:
    code = compile(f.read(), str(init_path), 'exec')
    exec(code, about)

root = Path(__file__).parent
long_desc = (root / "README.md").read_text(encoding="utf-8")

setup(
    name=about["__project__"],
    version=about["__version__"],
    description=about["__description__"],
    long_description=long_desc,
    long_description_content_type="text/markdown",
    author=about["__author__"],
    author_email=about["__email__"],
    url="https://github.com/phil/orac",
    license="MIT",
    python_requires=">=3.9",
    packages=find_packages(),
    include_package_data=True,
    package_data={"orac": ["prompts/*.yaml", "config.yaml"]},
    install_requires=[
        "google-generativeai>=0.3.0,<1",
        "openai>=1.23.0",
        "PyYAML>=6.0",
        "python-dotenv>=1.0.0",
        "loguru>=0.7.2",
    ],
    extras_require={"dev": ["pytest>=8.2", "ruff>=0.4.0"]},
    entry_points={"console_scripts": ["orac=orac.cli:main"]},
)
