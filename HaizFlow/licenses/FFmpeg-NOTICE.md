# FFmpeg Distribution Notice

The Windows artifact bundles `ffmpeg.exe` and `ffprobe.exe` from the Gyan FFmpeg 8.1.2 Essentials static build for Windows x64. The binaries report `--enable-gpl --enable-version3 --enable-static`, so this configured build is distributed under GPL-3.0-or-later rather than FFmpeg's default LGPL terms.

- Binary package: `ffmpeg-8.1.2-essentials_build.zip`
- Binary SHA-256: `db580001caa24ac104c8cb856cd113a87b0a443f7bdf47d8c12b1d740584a2ec`
- Upstream source: `ffmpeg-8.1.2.tar.xz`
- Source SHA-256: `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c`
- Source signature: `ffmpeg-8.1.2.tar.xz.asc`
- Gyan source commit reference: `38b88335f9`
- FFmpeg legal information: https://ffmpeg.org/legal.html
- Binary distributor and build information: https://www.gyan.dev/ffmpeg/builds/
- GPL-3.0 text included in this release: `GPL-3.0.txt`

The binary manifest, package README, license, signed upstream source archive and signature are included under `sources/ffmpeg` in the Windows artifact. Because the Essentials binary statically links covered third-party libraries, the release publisher must also make the complete corresponding source and build material for those libraries available through the same release channel. The included upstream FFmpeg tarball alone does not exhaust that obligation.
