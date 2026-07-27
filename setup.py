from setuptools import find_packages, setup

setup(
    name="voice-ai-studio-arabic",
    version="6.2.0",
    description="منصة صوتيات عربية لتوليد الصوت والأعمال اليمنية واستنساخ الصوت المصرح به",
    packages=find_packages(),
    python_requires=">=3.9,<3.14",
    entry_points={
        "console_scripts": [
            "voice-ai=main:app",
        ],
    },
)
