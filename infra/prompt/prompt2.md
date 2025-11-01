为catalog新增一个功能，
用于合并两个指定的实验

因为实际测试中可能会出现这样的情况，先测了1000个交替，然后器件没坏，就又接着测了5000个交替之类的。
但最后实际上我们是想让这6000个交替连在一起分析。

这个合并的功能实现以下操作

把这两个实验的h5文件合为一个，其中
可以指定以哪个实验的元数据为可信来源
但stepinfo要用各自自己的
并且比如原本是1-1001 1-5001 合并之后 就要是串在一起的1-6001

而且衔接处可以根据需要选择是否适当删去1-2个步骤，因为先测的最后一个步骤可能是不完整的就要删去，并且衔接了之后依然要保持 transfer transient交替的形式，所以在衔接处要判断是删除1个还是删除2个还是删除3个以满足这种交替的模式，而不会出现连续的相同步骤。

最后还要删除原来两个实验所对应的特征文件（如果生成了特征h5文件的话）

注意，json (test_info.json backup)中既包含实验元数据也包含步骤元数据，所以这个的更新有点复杂，实验元数据的部分要以我们指定为实验为准，而步骤元数据的部分要把两个实验的做合并，并且可能要重编序号
HDF5 File (Format Version 2.0_new_storage)
├── Root Attributes (experiment metadata)
├── /raw/ (原始数据备份)
│   ├── json (test_info.json backup)
│   └── workflow (workflow.json backup)
├── /transfer/ (Transfer数据 - 批量格式)
│   ├── step_info_table (展平的步骤信息，结构化数组)
│   └── measurement_data (3D数组: [步骤索引, 数据类型, 数据点])
└── /transient/ (Transient数据 - 批量格式)
    ├── step_info_table (展平的步骤信息，结构化数组)
    └── measurement_data (2D数组: [数据类型, 拼接的数据点])