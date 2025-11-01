ultrathink，我运行了python stability_report_pipeline.py --all-chips --output-dir "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/reports/"。发现pipeline还是有一些需要修改的
首先所有图片和视频应该是先保存到本地，然后再排布到ppt里
还有，前几页的图片有些是合成成了一张大图然后插入的，这是不对的，应该每个图片都是单独生成的，然后插入ppt进行排布。也就是说两阶段，第一阶段生成各种图片视频素材，第二阶段从磁盘读取这些素材进行排布生成ppt
另外，最后两页的信息没必要，删了吧
还有就是视频插入的方式好像不对，现在就是一张图片，视频没被正确插入。如果改成上面说的先保存为本地文件再插入ppt，应该就没问题了

请修改以上问题，但不需要帮我再次运行python stability_report_pipeline.py --all-chips --output-dir "/home/lidonghaowsl/develop_win/hdd/data/Stability_PS/reports/"
因为这个的运行要3个小时太久了