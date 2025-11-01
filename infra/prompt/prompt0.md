ultrathink，请完成以下任务
每个chip有最多6个device，deviceid从1到6以此对应的器件的封装的面积越来越大，留给半导体的工作区域越来越小，现在我们在探究这个封装面积对器件稳定性的影响。
接下来写一个pipeline脚本
最终是生成一个ppt文件包含丰富的报告

首先对于每个chip：
    第1页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = exp.plot_transient_all(figsize=(8, 6)) 的图
    第2页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = exp.plot_transfer_evolution(figsize=(8, 6)) 的图
    第3页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = exp.plot_transfer_evolution(figsize=(8, 6),log_scale=True) 的图
    第4页：分为6个子视频，对应的6个device，如果没有这个device就空白，每个子视频是该device的video_path = exp.create_transfer_video('视频输出路径.mp4', fps=30,figsize=(8, 6))视频
    第5页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = plotter.plot_transient_single(1, time_range=(5, 6),figsize=(8, 6)) 的图
    第6页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = plotter.plot_transient_single(1000, time_range=(5, 6),figsize=(8, 6)) 的图
    第7页：分为6个子图，对应的6个device，如果没有这个device就空白，每个子图是该device的fig = plotter.plot_transient_single(1000, time_range=(5, 6),figsize=(8, 6)) 的图
    第8页：分为6个子图，依次为
    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=0,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=1,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=5,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=0,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=1,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absI_max_raw'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=5,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )
    第9页：分为6个子图，依次为
    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=0,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=1,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=5,
        normalize_to_first=False,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=0,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=1,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )

    feature_name = 'absgm_max_forward'
    fig = plotter.plot_chip_feature(
        chip_id=chip_id,
        feature_name=feature_name,
        skip_points=5,
        normalize_to_first=True,
        markersize=0,
        figsize=(8, 6),
    )



其余的一切你能获取的信息都可以自由发挥的放在PPT里，尽可能详尽清晰，你是专业的科研助理，知道怎么做出高质量的科研报告PPT