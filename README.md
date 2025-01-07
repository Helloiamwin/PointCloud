Implement the Point Net model for Classifications and Segmentation tasks.

Dataset: S3DIS dataset (http://buildingparser.stanford.edu/dataset.html#Download)

The original architecture is likely below the image:


s3dis

    .
    ├── Area_1
    │    ├── hallway_1
    │    │    ├── color.npy
    │    │    ├── coord.npy
    │    │    ├── instance.npy
    │    │    ├── normal.npy
    │    │    └── segment.npy
    │    ├── hallway_2
    │    └── ......
    ├── Area_2
    └── ......

In some cases, the .hdf5 type is preferred.

s3dis-hdf5 (use SaveAsNpyToHdf5.ipynb to convert)

    .
    ├── Area_1
    │    ├── hallway_1_partition1.hdf5
    │    ├── hallway_1_partition2.hdf5
    │    ......
    │    ├── hallway_1_partition6.hdf5
    │    ├── hallway_2_partition1.hdf5
    │    └──......
    ├── Area_2
    └──.......


The two main files are PointNetCls.ipynb and PointNetSeg.ipynb respectively which are for Classification and Segmentation tasks.

Enjoy and leave your feelings!
