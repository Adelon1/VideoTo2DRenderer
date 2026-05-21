import time


def main():
    start_time = time.time()

    print()
    print("VideoTo2DRenderer pipeline")
    print("==========================")

    import getVideo
    import video_to_svg
    import svg_to_desmos_img
    import desmos_img_to_video

    #getVideo.main()
    video_to_svg.main()
    svg_to_desmos_img.main()
    desmos_img_to_video.main()

    elapsed = time.time() - start_time

    print()
    print("Pipeline finished.")
    print(f"Elapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
