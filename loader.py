import os
import cv2
import json
import torch
import random
import numpy as np
from utils.util import smoothing_mask, total_size
from PIL import Image
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from utils.augmentations import Transform
from sklearn.model_selection import StratifiedShuffleSplit


class ImageTransform():
    def __init__(self):
        pass
    
    def __call__(self):
        pass


class AppleDataset(Dataset):
    """
    Surface Defective Apple Dataset
    """
    def __init__(self, mode, data_path, img_size=(512, 512), transform=None, evaluation=None):
        self.data_path = data_path
        self.mode = mode
        self.img_size = img_size
        self.dataset, self.num_classes = self.load_data()
        self.transform = transform
        self.evaluation = evaluation
        
        n = len(self.dataset)
        # split = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=44) 
        # # labels = [int(sample['class']) for sample in self.dataset]
        # labels = [sample['class'] for sample in self.dataset]
        

        # for train_idx, valid_idx in split.split(self.dataset, labels):
        #     self.train_set = [self.dataset[i] for i in train_idx] 
        #     self.valid_set = [self.dataset[i] for i in valid_idx]
            
        # if mode == 'train':
        #     self.dataset = self.train_set
        # elif mode == 'valid':
        #     self.dataset = self.valid_set

        
        """Use for object detection splitting"""        
        if mode == 'train':
            self.dataset = self.dataset[:int(n*0.8)]
            
        elif mode == 'valid':
            self.dataset = self.dataset[int(n*0.8):]
            # random.shuffle(self.dataset)
        
    def __len__(self):
        return len(self.dataset)
    
    
    def __getitem__(self, idx):
        annotation, image_path, image = self.get_annotation(idx)
        sum_size = 1
        height, width = image.size
        
        if self.evaluation:
            return image, image_path, annotation
        
        # if self.transform:
        #     image = self.transform(image)
        
        # target_size = self.img_size[0], self.img_size[1]
        mask = np.zeros((self.img_size[0], self.img_size[1], self.num_classes), dtype=np.float32)
        area = np.zeros((self.img_size[0], self.img_size[1], self.num_classes), dtype=np.float32)
        
        target = np.array(annotation)
        boxes = target[:, :8] if target.shape[0]!=0 else None
        labels = target[:, 8] if target.shape[0]!=0 else None
        
        # Apply transform on `image`, `boxes`, `labels`
        image, boxes, labels = self.transform(image, boxes, labels)
        
        
        # Recompute the coordinate when image size changes
        # if boxes is not None:
            # target_h, target_w = self.img_size[0], self.img_size[1]
            # new_wh = np.array([target_w / width, target_h / height]) # rescaling factor
            # boxes = boxes * np.tile(new_wh, 4)
            
        # labels = labels.astype(np.int32)
        
        num_obj = len(boxes) if boxes is not None else 1
        sum_size = total_size(boxes)
        
        for box, label in zip(boxes, labels):
            mask, area = smoothing_mask(mask, area, box, sum_size/num_obj, label)
        
        image, mask, area = self.annotation_transform(np.array(image), mask, area, self.img_size[1], self.img_size[1])
                         
        image = torch.from_numpy(np.array(image)).permute(2, 0, 1).float()
        mask = torch.from_numpy(mask.astype(np.float32))
        area = torch.from_numpy(area.astype(np.float32))
        sum_size = torch.from_numpy(np.array([sum_size], dtype=np.float32))
           
        return image, mask, area, sum_size
    
    
    def annotation_transform(self, image, mask, area, height, width):
        resize_img = cv2.resize(image, (width, height))
        resized_mask = cv2.resize(mask, (width, height))
        resized_area = cv2.resize(area, (width, height))
        return resize_img, resized_mask, resized_area
    
    
    def load_data(self):
        # read ground truth json file
        with open(os.path.join(self.data_path, 'ground-truth','new_gt_multi.json')) as f:
            data = json.load(f)
        
        filtered_data = [item for item in data if set(item['class_id']) in ({1}, {3}, {1, 3})]
        
        label_mapping = {1: 0, 3: 1}
        for data in filtered_data:
            data['class_id'] = [label_mapping[i] for i in data['class_id']]
        
        unique_classes = set()
        for data in filtered_data:
            unique_classes.update(data['class_id'])
        
        num_classes = len(unique_classes)
        
        return filtered_data, num_classes


    def get_annotation(self, idx):
        sample = self.dataset[idx]
        
        image_path = os.path.join(self.data_path, 'images', f"{sample['name']}.jpg")
        # class_id = int(sample['class'])
        image = Image.open(image_path).convert('RGB')
        width, height = image.size
        
        temp_boxes = sample['crop_coordinates_ratio']
        class_ids = sample['class_id']
        annotations = []
        
        # convert format from [cx, cy, w, h] -> [x1, y1, x2, y2, x3, y3, x4, y4, class_id]
        for box, class_id in zip(temp_boxes, class_ids):
            # print(class_id)
            cx, cy, w, h = box
            x1 = int((cx - w / 2) * width)
            y1 = int((cy - h / 2) * height)
            x2 = int((cx + w / 2) * width)
            y2 = int((cy - h / 2) * height)
            x3 = int((cx + w / 2) * width)
            y3 = int((cy + h / 2) * height)
            x4 = int((cx - w / 2) * width)
            y4 = int((cy + h / 2) * height)
            
            # perform boundary checks
            x1 = max(0, min(x1, width - 1))
            y1 = max(0, min(y1, height - 1))
            x2 = max(0, min(x2, width - 1))
            y2 = max(0, min(y2, height - 1))
            x3 = max(0, min(x3, width - 1))
            y3 = max(0, min(y3, height - 1))
            x4 = max(0, min(x4, width - 1))
            y4 = max(0, min(y4, height - 1))

            annotations.append([x1, y1, x2, y2, x3, y3, x4, y4, class_id])
                   
        return annotations, image_path, image 


if __name__ == '__main__':
    
    """For Apple Dataset"""
    transform_train = Transform(is_train=True, size=(512, 512))
    appledata = AppleDataset(mode='valid',
                             data_path='/root/data/apple/cropped-apple-bb/',
                             img_size=(512, 512),
                             transform=transform_train)
    
    apple_loader = DataLoader(appledata, batch_size=2, shuffle=True)
    for batch in apple_loader:
        images, masks, areas, total_sizes = batch
        # import pdb; pdb.set_trace()
    
    