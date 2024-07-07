# Built-in modules
import os, argparse

def truncate (s, n):
    """Truncate string s to length n"""
    return s[:n]

if __name__ == "__main__":
    parser = argparse.ArgumentParser (
        description = "Truncate gpx files to match a video",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """\
""" # TODO: Add epilog
    )
