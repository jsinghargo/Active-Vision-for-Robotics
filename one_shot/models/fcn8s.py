import torch
from torch import nn
from torchvision import models
import sys
import os
import pdb
from one_shot.utils import get_upsampling_weight
from one_shot.models.config import vgg16_path
import torch.nn.functional as F


# This is implemented in full accordance with the original one (https://github.com/shelhamer/fcn.berkeleyvision.org)
class FCN8s(nn.Module):
	def __init__(self, num_classes, pretrained=True, caffe=False):
		super(FCN8s, self).__init__()
		vgg = models.vgg16()
		if pretrained:
			if caffe:
				# load the pretrained vgg16 used by the paper's author
				vgg.load_state_dict(torch.load(vgg16_caffe_path))
			else:
				vgg.load_state_dict(torch.load(vgg16_path))
		features, classifier = list(vgg.features.children()), list(vgg.classifier.children())

		'''
		100 padding for 2 reasons:
		    1) support very small input size
		    2) allow cropping in order to match size of different layers' feature maps
		Note that the cropped part corresponds to a part of the 100 padding
		Spatial information of different layers' feature maps cannot be align exactly because of cropping, which is bad
		'''
		features[0].padding = (100, 100)

		for f in features:
			if 'MaxPool' in f.__class__.__name__:
				f.ceil_mode = True
			elif 'ReLU' in f.__class__.__name__:
				f.inplace = True

		self.features3 = nn.Sequential(*features[: 17])
		self.features4 = nn.Sequential(*features[17: 24])
		self.features5 = nn.Sequential(*features[24:])

		self.score_pool3 = nn.Conv2d(512, num_classes, kernel_size=1) # changed
		self.score_pool4 = nn.Conv2d(1024, num_classes, kernel_size=1) # changed
		# self.score_pool3.weight.data.zero_()
		# self.score_pool3.bias.data.zero_()
		# self.score_pool4.weight.data.zero_()
		# self.score_pool4.bias.data.zero_()

		fc6 = nn.Conv2d(1024, 4096, kernel_size=7) #changed
		# fc6.weight.data.copy_(classifier[0].weight.data.view(4096, 512, 7, 7))
		# fc6.bias.data.copy_(classifier[0].bias.data)
		fc7 = nn.Conv2d(4096, 4096, kernel_size=1)
		# fc7.weight.data.copy_(classifier[3].weight.data.view(4096, 4096, 1, 1))
		# fc7.bias.data.copy_(classifier[3].bias.data)
		score_fr = nn.Conv2d(4096, num_classes, kernel_size=1)
		# score_fr.weight.data.zero_()
		# score_fr.bias.data.zero_()
		self.score_fr = nn.Sequential(
		    fc6, nn.ReLU(inplace=True), nn.Dropout(), fc7, nn.ReLU(inplace=True), nn.Dropout(), score_fr
		)

		self.upscore2 = nn.ConvTranspose2d(num_classes, num_classes, kernel_size=4, stride=2, bias=False)
		self.upscore_pool4 = nn.ConvTranspose2d(num_classes, num_classes, kernel_size=4, stride=2, bias=False)
		self.upscore8 = nn.ConvTranspose2d(num_classes, num_classes, kernel_size=16, stride=8, bias=False)
		self.upscore2.weight.data.copy_(get_upsampling_weight(num_classes, num_classes, 4))
		self.upscore_pool4.weight.data.copy_(get_upsampling_weight(num_classes, num_classes, 4))
		self.upscore8.weight.data.copy_(get_upsampling_weight(num_classes, num_classes, 16))

	def forward(self, x, target):
		x_size = x.size()
		# vgg features for both current image and target image
		pool3_cur = self.features3(x)
		pool3_tar = self.features3(target)

		# concat curr and target pool3
		pool3_tar_max = F.max_pool2d(pool3_tar, pool3_tar.shape[-1])
		pool3_tar_rep = pool3_tar_max.expand(-1,-1,pool3_cur.shape[-2],pool3_cur.shape[-1])
		pool3_cat = torch.cat([pool3_cur, pool3_tar_rep], 1)

		pool4_cur = self.features4(pool3_cur)
		pool4_tar = self.features4(pool3_tar)

		# concat curr and target pool4
		pool4_tar_max = F.max_pool2d(pool4_tar, pool4_tar.shape[-1])
		pool4_tar_rep = pool4_tar_max.expand(-1,-1,pool4_cur.shape[-2],pool4_cur.shape[-1])
		pool4_cat = torch.cat([pool4_cur, pool4_tar_rep], 1)

		pool5_cur = self.features5(pool4_cur)
		pool5_tar = self.features5(pool4_tar)

		# concat curr and target pool3
		pool5_tar_max = F.max_pool2d(pool5_tar, pool5_tar.shape[-1])
		pool5_tar_rep = pool5_tar_max.expand(-1,-1,pool5_cur.shape[-2],pool5_cur.shape[-1])
		pool5_cat = torch.cat([pool5_cur, pool5_tar_rep], 1)

		score_fr = self.score_fr(pool5_cat)
		upscore2 = self.upscore2(score_fr)

		score_pool4 = self.score_pool4(0.01 * pool4_cat)
		upscore_pool4 = self.upscore_pool4(score_pool4[:, :, 5: (5 + upscore2.size()[2]), 5: (5 + upscore2.size()[3])]
		                                   + upscore2)

		score_pool3 = self.score_pool3(0.0001 * pool3_cat)
		upscore8 = self.upscore8(score_pool3[:, :, 9: (9 + upscore_pool4.size()[2]), 9: (9 + upscore_pool4.size()[3])]
		                         + upscore_pool4)
		return upscore8[:, :, 31: (31 + x_size[2]), 31: (31 + x_size[3])].contiguous()
