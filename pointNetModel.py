import torch
import torch.nn as nn
import torch.nn.functional as F

class Tnet (nn.Module):
  def __init__(self, dim , num_points = 2500):
    super(Tnet, self).__init__()
    self.dim = dim

    self.conv1 = nn.Conv1d(dim, 64, kernel_size=1)
    self.conv2 = nn.Conv1d(64, 128, kernel_size = 1)
    self.conv3 = nn.Conv1d(128, 1024, kernel_size = 1)

    self.linear1 = nn.Linear(1024, 512)
    self.linear2 = nn.Linear(512, 256)
    self.linear3 = nn.Linear(256, dim ** 2)

    self.bn1 = nn.BatchNorm1d(64)
    self.bn2 = nn.BatchNorm1d(128)
    self.bn3 = nn.BatchNorm1d(1024)
    self.bn4 = nn.BatchNorm1d(512)
    self.bn5 = nn.BatchNorm1d(256)

    self.max_pool = nn.MaxPool1d(kernel_size = num_points)

  def forward(self, x):
    bs = x.shape[0]

    # pass though shared MLP layers (conv1d)
    x = self.bn1(F.relu(self.conv1(x)))
    x = self.bn2(F.relu(self.conv2(x)))
    x = self.bn3(F.relu(self.conv3(x)))

    # max pool over num points
    x = self.max_pool(x).view(bs, -1)

    # pass through MLP
    x = self.bn4(F.relu(self.linear1(x)))
    x = self.bn5(F.relu(self.linear2(x)))
    x = self.linear3(x)

    # initialize identity matrix
    iden  = torch.eye(self.dim, requires_grad=True).repeat(bs, 1, 1)
    if x.is_cuda:
      iden = iden.cuda()

    x = x.view(-1, self.dim, self.dim) + iden

    return x


class PointNetBackbone(nn.Module):
    def __init__(self, num_points = 2500, num_global_feats= 1024, local_feat=False):
        super(PointNetBackbone, self).__init__()
        self.num_points = num_points
        self.num_global_feats = num_global_feats
        self.local_feat = local_feat

        # Spatial Transformer Networks (T-nets)
        self.tnet1 = Tnet(dim=3, num_points=num_points)
        self.tnet2 = Tnet(dim=64, num_points=num_points)

        # shared MLP 1
        self.conv1 = nn.Conv1d(3, 64, kernel_size=1)
        self.conv2 = nn.Conv1d(64, 64, kernel_size=1)
        
        # shared MLP 2
        self.conv3 = nn.Conv1d(64, 64, kernel_size=1)
        self.conv4 = nn.Conv1d(64, 128, kernel_size=1)
        self.conv5 = nn.Conv1d(128, self.num_global_feats, kernel_size=1)

        # batch norms forr both shared MLPs
        self.bn1 = nn.BatchNorm1d(64)
        self.bn2 = nn.BatchNorm1d(64)
        self.bn3 = nn.BatchNorm1d(64)
        self.bn4 = nn.BatchNorm1d(128)
        self.bn5 = nn.BatchNorm1d(self.num_global_feats)

        # max pool to get the global features
        self.max_pool = nn.MaxPool1d(kernel_size=num_points, return_indices=True)

    def forward(self, x):
        bs = x.shape[0]

        A_input = self.tnet1(x)
        x = torch.bmm(x.transpose(2,1), A_input).transpose(2,1)
        
        # pass through first shared MLP
        x = self.bn1(F.relu(self.conv1(x)))
        x = self.bn2(F.relu(self.conv2(x)))
        
        # get feature transform
        A_feat = self.tnet2(x)
        
        # perform 2nd transformation
        x = torch.bmm(x.transpose(2,1), A_feat).transpose(2,1)
        
        local_features = x.clone() # n x 64

        # pass through second shared MLP
        x = self.bn3(F.relu(self.conv3(x)))
        x = self.bn4(F.relu(self.conv4(x)))
        x = self.bn5(F.relu(self.conv5(x)))
        
        # get global feature vector and critical indexes
        global_features, critical_indexes = self.max_pool(x)
        global_features = global_features.view(bs, -1)
        critical_indexes = critical_indexes.view(bs, -1)
        
        if self.local_feat: # for segment mode
            features = torch.cat((local_features, global_features.unsqueeze(-1).repeat(1, 1, self.num_points)), dim=1)
            return features, critical_indexes, A_feat
        else:
            return global_features, critical_indexes, A_feat
        
        
class PointNetClassHead(nn.Module):
    def __init__(self, num_points=2500, num_global_feats=1024, k=2):
        super(PointNetClassHead, self).__init__()
        
        self.backbone = PointNetBackbone(num_points, num_global_feats, local_feat=False)
        
        # MLP for classification
        self.linear1 = nn.Linear(num_global_feats, 512)
        self.linear2 = nn.Linear(512, 256)
        self.linear3 = nn.Linear(256, k)
        
        # batchnorm for the first 2 linear layers
        self.bn1 = nn.BatchNorm1d(512)
        self.bn2 = nn.BatchNorm1d(256)
        
        self.dropout = nn.Dropout(p=0.3)
        
    def forward(self, x):
        x, crit_idxs, A_feat = self.backbone(x)
        
        x = self.bn1(F.relu(self.linear1(x)))
        x = self.bn2(F.relu(self.linear2(x)))
        x = self.dropout(x)
        x = self.linear3(x)
        
        # return logits
        return x, crit_idxs, A_feat
        
        
# Segmentation Head
class PointNetSegHead(nn.Module):
    ''' Segmentation Head '''
    def __init__(self, num_points=2500, num_global_feats=1024, m=2):
        super(PointNetSegHead, self).__init__()

        self.num_points = num_points
        self.m = m

        # get the backbone 
        self.backbone = PointNetBackbone(num_points, num_global_feats, local_feat=True)

        # shared MLP
        num_features = num_global_feats + 64 # local and global features
        self.conv1 = nn.Conv1d(num_features, 512, kernel_size=1)
        self.conv2 = nn.Conv1d(512, 256, kernel_size=1)
        self.conv3 = nn.Conv1d(256, 128, kernel_size=1)
        self.conv4 = nn.Conv1d(128, m, kernel_size=1)

        # batch norms for shared MLP
        self.bn1 = nn.BatchNorm1d(512)
        self.bn2 = nn.BatchNorm1d(256)
        self.bn3 = nn.BatchNorm1d(128)

    def forward(self, x):
        
        # get combined features
        x, crit_idxs, A_feat = self.backbone(x) 

        # pass through shared MLP
        x = self.bn1(F.relu(self.conv1(x)))
        x = self.bn2(F.relu(self.conv2(x)))
        x = self.bn3(F.relu(self.conv3(x)))
        x = self.conv4(x)

        x = x.transpose(2, 1)
        
        return x, crit_idxs, A_feat


def TestModel():
    test_data = torch.rand(32, 3, 2500)
    tnet = Tnet(dim = 3)
    transform = tnet(test_data)
    print(f"T-net output shape: {transform.shape}")
    
    # test backbone
    pointfeat = PointNetBackbone(local_feat=False)
    out, _, _ = pointfeat(test_data)
    print(f"Global Features shape: {out.shape}")
    
    pointfeat = PointNetBackbone(local_feat=True)
    out, _, _ = pointfeat(test_data)
    print(f"Combined Features shape: {out.shape}")
    
    # pointfeat = PointNetBackbone(local_feat=True).eval()
    # out, _, _ = pointfeat(test_data[0,:,:]).unsqueeze(0)
    
    classifier = PointNetClassHead(k = 5)
    out, _, _ = classifier(test_data)
    print(f"Class output shape: {out.shape}")
    
    classifier = PointNetClassHead(k=5).eval()
    out, _, _ = classifier(test_data[0, :, :].unsqueeze(0))
    
    ## test segmentation head
    seg = PointNetSegHead(m=3)
    out, _, _ = seg(test_data)
    print(f'Seg shape: {out.shape}')
    
    SegHead = PointNetSegHead(m=3).eval()
    out, _, _ = SegHead(test_data[0, :, :].unsqueeze(0))
    print(f'Seg shape: {out.shape}')    

import open3d as o3
from shapenet_dataset import ShapenetDataset, read_pointnet_colors
from open3d.web_visualizer import draw 
def show_3d_visualization(sample_dataset):
    points, seg = sample_dataset
    pcd = o3.geometry.PointCloud()
    pcd.points = o3.utility.Vector3dVector(points)
    pcd.colors = o3.utility.Vector3dVector(read_pointnet_colors(seg.numpy()))
    o3.visualization.draw_plotly([pcd])
    # draw(pcd, point_size=3) # for non colab
    # 
    
    
if __name__ == "__main__":
    
    TestModel()
    import os
    ROOT = os.getcwd() + r"\archive\shapenet\shapenetcore_partanno_segmentation_benchmark_v0"
    sample_dataset = train_dataset = ShapenetDataset(ROOT, npoints=20000, split='train', classification=False, normalize=False)
    show_3d_visualization(sample_dataset[1009])