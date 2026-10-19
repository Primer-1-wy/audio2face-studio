"""Fetch NVIDIA's public Reallusion Debra Audio2Face sample, preserving sources."""
import download_official_claire as download

download.DEST = download.ROOT / 'assets/debra-official'
download.PREFIX = 'Assets/Audio2Face/Samples_2023.2/reallusion/Debra_A2F_CC_GameBase/'

if __name__ == '__main__':
    download.main()
