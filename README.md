# mcap-to-mp4

A tool to convert ROS topics recored with [mcap](https://mcap.dev/) to MP4 file

## Requirements

* ffmpeg

## QuickStart

```
docker build -t tiryoh/mcap-to-mp4 .
```

```
docker run --rm -it -v "$(PWD):/works" tiryoh/mcap-to-mp4 bash
```


## License

MIT License

 Copyright 2024 Daisuke Sato
