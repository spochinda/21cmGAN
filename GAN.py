import argparse
import itertools
import numpy as np
import tensorflow as tf
from scipy.io import loadmat
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.animation import FuncAnimation, PillowWriter
import tqdm
import time
import os
import pickle
from models.wgan import *
#add in second inception module (done)
#layer normalisation

print("Inside GAN.py", flush=True)

parser = argparse.ArgumentParser(description="GAN to learn simulation cubes from initial conditions and smaller cubes")
parser.add_argument('--index', type=int, default=0, help='An index from 0 to 20 to pick a set of learning rates and penalty strengths')
args = parser.parse_args()
index = args.index

path = os.getcwd()


print("Available devices: ", tf.config.list_physical_devices(), flush=True)

"""
#i=0, i*24:(i+1)*24 = 0:24, 
#1. Load data
dir_files = os.listdir(path + '/outputs')
rng =range(1000,1010)
z = np.arange(6,28.1,1)
T21_target = np.zeros((len(rng)*24, 128, 128, 128, len(z)))
T21_train = np.zeros((len(rng)*24, 64, 64, 64, len(z)))
test = np.zeros((len(rng)*24, 64, 64, 64, len(z)))
delta = np.zeros((len(rng)*24, 128, 128, 128))
vbv = np.zeros((len(rng)*24, 128, 128, 128))
files = []
for i,ID in enumerate(rng):
    files_ = [file for file in dir_files if (str(ID) in file) and ('T21_cube' in file)]
    #sort files by redshift
    files.append(sorted(files_, key=lambda x: float(x.split('_')[2])))

"""

class DataManager:
    def __init__(self, path, redshifts=[16], IC_seeds=[1000,1001]):
        self.path = path
        self.redshifts = redshifts
        self.IC_seeds = IC_seeds

    def get_file_lists(self):
        assert isinstance(self.redshifts, list), "redshifts must be a list"
        assert isinstance(self.IC_seeds, list), "IC_seeds must be a list"
        dir_T21 = os.listdir(self.path + '/outputs')
        T21_files = np.empty(shape=(len(self.IC_seeds), len(self.redshifts)), dtype=object)
        for file in dir_T21:
            if 'T21_cube' in file:
                z = int(file.split('_')[2])
                ID = int(file.split('_')[7])
                if (z in self.redshifts) and (ID in self.IC_seeds):
                    #print ID index in IC_seeds:
                    T21_files[self.IC_seeds.index(ID), self.redshifts.index(z)] = file
        
        dir_IC = os.listdir(self.path + '/IC')
        delta_files = np.empty(shape=(len(self.IC_seeds)), dtype=object)
        vbv_files = np.empty(shape=(len(self.IC_seeds)), dtype=object)
        for file in dir_IC:
            if 'delta' in file:
                ID = int(file.split('delta')[1].split('.')[0])
                if ID in self.IC_seeds:
                    delta_files[self.IC_seeds.index(ID)] = file
            elif 'vbv' in file:
                ID = int(file.split('vbv')[1].split('.')[0])
                if ID in self.IC_seeds:
                    vbv_files[self.IC_seeds.index(ID)] = file
        
        return T21_files, delta_files, vbv_files
    
    def generator_func(self, augment=False, augments=24, low_res=False):
        assert len(self.redshifts) == 1, "generator_func only works for one redshift at a time"
        T21_files, delta_files, vbv_files = self.get_file_lists()
        #print(T21_files,augments)
        if augment:
            augs = np.array([np.random.choice(24, size=augments, replace=False) for i in range(len(delta_files))]) #might need shuffling 
            #print(augs)
            #k=0
            for i in range(augments):
                #print("test: ", augs[:,i])
                #print("test2: ", T21_files[0],delta_files,vbv_files,augs[:,i])
                for j,(T21_file, delta_file, vbv_file, aug) in enumerate(zip(T21_files,delta_files,vbv_files,augs[:,i])):
                    #k+=1
                    #print(T21_file[0].split('_')[7], delta_file.split("delta")[1].split(".")[0], vbv_file.split("vbv")[1].split(".")[0], aug)
                    #print("j={0}, k={1}".format(j,k))
                    T21 = loadmat(self.path + '/outputs/' + T21_file[0])['Tlin']
                    delta = loadmat(self.path + '/IC/' + delta_file)['delta']
                    vbv = loadmat(self.path + '/IC/' + vbv_file)['vbv']

                    T21 = self.augment_data(T21, augments=aug).reshape(1,128,128,128,1)
                    delta = self.augment_data(delta, augments=aug).reshape(1,128,128,128,1)
                    vbv = self.augment_data(vbv, augments=aug).reshape(1,128,128,128,1)
                    if low_res:
                        T21_lr = tf.keras.layers.GaussianNoise(tf.reduce_mean(T21)*0.05)(T21)
                        T21_lr = tf.keras.layers.Conv3D(filters=1, kernel_size=(2, 2, 2),
                                                                       kernel_initializer=tf.keras.initializers.constant(value=1/8),
                                                                       use_bias=False, bias_initializer=None, #tf.keras.initializers.Constant(value=0.1),
                                                                       strides=(2, 2, 2), padding='valid', data_format="channels_last", 
                                                                       activation=None,
                                                                       )(T21_lr)                        
                    else:
                        T21_lr = T21[:,:64,:64,:64,:]
                    
                    
                    T21 = tf.cast(tf.reshape(T21, (128,128,128,1)), dtype=tf.float32)
                    delta = tf.cast(tf.reshape(delta, (128,128,128,1)), dtype=tf.float32)
                    vbv = tf.cast(tf.reshape(vbv, (128,128,128,1)), dtype=tf.float32)
                    T21_lr = tf.cast(tf.reshape(T21_lr, (64,64,64,1)), dtype=tf.float32)
                    yield T21, delta, vbv, T21_lr
        else:
            for j,(T21_file, delta_file, vbv_file) in enumerate(zip(T21_files,delta_files,vbv_files)):
                T21 = loadmat(self.path + '/outputs/' + T21_file[0])['Tlin']
                delta = loadmat(self.path + '/IC/' + delta_file)['delta']
                vbv = loadmat(self.path + '/IC/' + vbv_file)['vbv']
                T21_lr = T21[:64,:64,:64]
                
                T21_lr = tf.cast(tf.reshape(T21_lr, (64,64,64,1)), dtype=tf.float32)
                T21 = tf.cast(tf.reshape(T21, (128,128,128,1)), dtype=tf.float32)
                delta = tf.cast(tf.reshape(delta, (128,128,128,1)), dtype=tf.float32)
                vbv = tf.cast(tf.reshape(vbv, (128,128,128,1)), dtype=tf.float32)
                print(j, T21.shape, delta.shape, vbv.shape, T21_lr.shape)
                yield T21, delta, vbv, T21_lr
            
    
        


    def load(self):
        T21_files, delta_files, vbv_files = self.get_file_lists()
        T21 = np.zeros((len(self.IC_seeds), 128, 128, 128, len(self.redshifts)), dtype=np.float32)
        delta = np.zeros((len(self.IC_seeds), 128, 128, 128), dtype=np.float32)
        vbv = np.zeros((len(self.IC_seeds), 128, 128, 128), dtype=np.float32)
        for i,file in enumerate(T21_files):
            delta[i] = loadmat(self.path + '/IC/' + delta_files[i])['delta']
            vbv[i] = loadmat(self.path + '/IC/' + vbv_files[i])['vbv']
            for j,file_ in enumerate(file):
                T21[i,:,:,:,j] = loadmat(self.path + '/outputs/' + file_)['Tlin']
        return T21, delta, vbv
    
    def data(self, augment=False, augments=23, low_res=False):
        #augments: number of augmented data per IC seed. Always includes the unaltered box
        T21, delta, vbv = self.load()
        if augment:
            assert (augments <= 23) and (augments>=1), "augments must be between 1 and 23"
            delta_augmented = np.empty(((augments+1)*len(self.IC_seeds), 128, 128, 128), dtype=np.float32)
            vbv_augmented = np.empty(((augments+1)*len(self.IC_seeds), 128, 128, 128), dtype=np.float32)
            T21_augmented = np.empty(((augments+1)*len(self.IC_seeds), 128, 128, 128, len(self.redshifts)), dtype=np.float32)

            for i in range(len(self.IC_seeds)):
                augs = [*np.random.choice(23, size=augments, replace=True), 23]
                delta_augmented[i*(augments+1):(i+1)*(augments+1)] = self.augment_data(delta[i], augments=augs)
                vbv_augmented[i*(augments+1):(i+1)*(augments+1)] = self.augment_data(vbv[i], augments=augs)
                for j in range(len(self.redshifts)):
                    T21_augmented[i*(augments+1):(i+1)*(augments+1),:,:,:,j] = self.augment_data(T21[i,:,:,:,j], augments=augs)
            T21 = tf.cast(T21_augmented, dtype=tf.float32)
            delta = tf.expand_dims(input=tf.cast(delta_augmented, dtype=tf.float32), axis=4)
            vbv = tf.expand_dims(input=tf.cast(vbv_augmented, dtype=tf.float32), axis=4)
        else:
            T21 = tf.cast(T21, dtype=tf.float32)
            delta = tf.expand_dims(input=tf.cast(delta, dtype=tf.float32), axis=4)
            vbv = tf.expand_dims(input=tf.cast(vbv, dtype=tf.float32), axis=4)

        if low_res:
            T21_lr = np.empty((T21.shape[0], 64, 64, 64, T21.shape[-1]), dtype=np.float32)
            for i in range(T21.shape[0]):
                for j in range(T21.shape[-1]):
                    temp = tf.reshape(T21[i,:,:,:,j], (1,128,128,128,1))
                    #add 5% gaussian noise
                    #temp = tf.keras.layers.GaussianNoise(tf.reduce_mean(temp)*0.1)(temp)
                    #T21_lr[i,:,:,:,j] = tf.keras.layers.Conv3D(filters=1, kernel_size=(2, 2, 2),
                    #                                           kernel_initializer=tf.keras.initializers.constant(value=1/8),#GaussianKernelInitializer(stddev=0.5, size=2)
                    #                                           use_bias=False, bias_initializer=None, #tf.keras.initializers.Constant(value=0.1),
                    #                                           strides=(2, 2, 2), padding='valid', data_format="channels_last", 
                    #                                           activation=None,
                    #                                           )(temp).numpy().reshape(64,64,64)
                    #try average pooling 
                    #T21_lr[i,:,:,:,j] = tf.keras.layers.AveragePooling3D(pool_size=(2, 2, 2), strides=(2, 2, 2), padding='valid', data_format="channels_last")(temp).numpy().reshape(64,64,64)  
                    T21_lr[i,:,:,:,j] = temp[0,::2,::2,::2,0].numpy()
                    
                    #fig,axes = plt.subplots(1,1,figsize=(10,5))
                    #axes[0].imshow(T21[i,:,:,64,j])
                    #axes[1].imshow(T21_lr[i,:,:,32,j])
                    #histograms instead
                    #axes.hist(T21[i,:,:,:,j].numpy().flatten(), density=True, bins=100, alpha=0.5, label="real")
                    #axes.hist(T21_lr[i,:,:,:,j].flatten(), density=True, bins=100, alpha=0.5, label="fake")
                    #axes.legend()
                    #plt.show()
                    
            T21_lr = tf.cast(T21_lr, dtype=tf.float32)
        else:
            T21_lr = None
        return T21, delta, vbv, T21_lr

    def augment_data(self, x, augments=23):
        y = np.empty((24,*x.shape))

        y[0,:,:,:] = x[::-1, ::-1, :]
        y[1,:,:,:] = x[::-1, :, ::-1]
        y[2,:,:,:] = x[:, ::-1, ::-1]
        
        y[3,:,:,:] = tf.transpose(x, (1, 0, 2))[::-1, :, :]
        y[4,:,:,:] = tf.transpose(x, (1, 0, 2))[::-1, :, ::-1]
        y[5,:,:,:] = tf.transpose(x, (1, 0, 2))[:, ::-1, :]
        y[6,:,:,:] = tf.transpose(x, (1, 0, 2))[:, ::-1, ::-1]

        y[7,:,:,:] = tf.transpose(x, (2, 1, 0))[::-1, :, :]
        y[8,:,:,:] = tf.transpose(x, (2, 1, 0))[::-1, ::-1, :]
        y[9,:,:,:] = tf.transpose(x, (2, 1, 0))[:, :, ::-1]
        y[10,:,:,:] = tf.transpose(x, (2, 1, 0))[:, ::-1, ::-1]

        y[11,:,:,:] = tf.transpose(x, (0, 2, 1))[:, ::-1, :]
        y[12,:,:,:] = tf.transpose(x, (0, 2, 1))[::-1, ::-1, :]
        y[13,:,:,:] = tf.transpose(x, (0, 2, 1))[:, :, ::-1]
        y[14,:,:,:] = tf.transpose(x, (0, 2, 1))[::-1, :, ::-1]

        y[15,:,:,:] = tf.transpose(x, (1, 2, 0))[::-1, ::-1, :]
        y[16,:,:,:] = tf.transpose(x, (1, 2, 0))[:, ::-1, ::-1]
        y[17,:,:,:] = tf.transpose(x, (1, 2, 0))[::-1, :, ::-1]
        y[18,:,:,:] = tf.transpose(x, (1, 2, 0))[::-1, ::-1, ::-1]
        
        y[19,:,:,:] = tf.transpose(x, (2, 0, 1))[::-1, ::-1, :]
        y[20,:,:,:] = tf.transpose(x, (2, 0, 1))[::-1, :, ::-1]
        y[21,:,:,:] = tf.transpose(x, (2, 0, 1))[:, ::-1, ::-1]
        y[22,:,:,:] = tf.transpose(x, (2, 0, 1))[::-1, ::-1, ::-1]
        y[23,:,:,:] = x
        
        return y[augments,:,:,:]



Data = DataManager(path, redshifts=list(np.arange(6,28,1)), IC_seeds=list(range(1000,1002)))

dataset = tf.data.Dataset.from_generator(Data.generator_func,
                                         args=(True, 6, True),
                                         output_signature=(
                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),  # Modify target_shape
                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),
                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),
                                             tf.TensorSpec(shape=(64,64,64,1), dtype=tf.float32)
                                             ))



def standardize(data, data_stats):
    mean, var = tf.nn.moments(data_stats, axes=[1,2,3], keepdims=True) #mean across xyz with shape=(batch,x,y,z,channels)
    mean = mean.numpy()
    var = var.numpy()
    for i,(m,v) in enumerate(zip(mean,var)):
        if m==0 and v==0:
            mean[i] = 0
            var[i] = 1
            #print("mean and var both zero for i={0} j={1}, setting mean to {2} and var to {3}".format(i,np.nan,mean[i],var[i]))
    std = var**0.5
    return (data - mean) / std

def plot_and_save(IC_seeds, redshift, sigmas, plot_slice=True):
    fig = plt.figure(tight_layout=True, figsize=(20,10))
    gs = gridspec.GridSpec(len(IC_seeds)+1, 6, figure=fig)
    ax_loss = fig.add_subplot(gs[0,:])

    #loss row
    ax_loss.plot(range(len(generator_losses_epoch)), generator_losses_epoch, label="generator")
    ax_loss.plot(range(len(critic_losses_epoch)), critic_losses_epoch, label="critic")
    ax_loss.plot(range(len(gradient_penalty_epoch)), gradient_penalty_epoch, label="gradient penalty")
    ax_loss.set_title("lambda={0}, learning rate={1}".format(lbda, learning_rate))
    ax_loss.set_xlabel("Epoch")
    ax_loss.set_ylabel("Loss")
    ax_loss.legend()

    # Validation data
    Data_validation = DataManager(path, redshifts=[redshift,], IC_seeds=IC_seeds)
    T21, delta, vbv, T21_lr = Data_validation.data(augment=False, augments=9, low_res=True) 
    T21_standardized = standardize(T21, T21_lr)
    T21_lr_standardized = standardize(T21_lr, T21_lr)
    vbv_standardized = standardize(vbv, vbv)
    generated_boxes = generator(T21_lr_standardized, delta, vbv_standardized).numpy()

    for i,IC in enumerate(IC_seeds):
        # Plot histograms
        ax_hist = fig.add_subplot(gs[i+1,0])
        ax_hist.hist(generated_boxes[i, :, :, :, 0].flatten(), bins=100, alpha=0.5, label="generated", density=True)
        ax_hist.hist(T21_standardized[i, :, :, :, 0].numpy().flatten(), bins=100, alpha=0.5, label="real", density=True)
        ax_hist.set_xlabel("Standardized T21")
        ax_hist.set_title("Histograms of standardized data")
        ax_hist.legend()

        # Plot real and generated data
        T21_std = np.std(T21_standardized[i, :, :, :, 0].numpy().flatten())
        ax_gen = fig.add_subplot(gs[i+1,1])
        ax_gen.imshow(generated_boxes[i, :, :, 64, 0], vmin=-sigmas*T21_std, vmax=sigmas*T21_std)
        ax_gen.set_title("Generated")
        ax_real = fig.add_subplot(gs[i+1,2])
        ax_real.imshow(T21_standardized[i, :, :, 64, 0], vmin=-sigmas*T21_std, vmax=sigmas*T21_std)
        ax_real.set_title("Real")
        ax_real_lr = fig.add_subplot(gs[i+1,3])
        ax_real_lr.imshow(T21_lr_standardized[i, :, :, 32, 0], vmin=-sigmas*T21_std, vmax=sigmas*T21_std)
        ax_real_lr.set_title("Real lr")

        if plot_slice:
            ax_delta = fig.add_subplot(gs[i+1,4])
            delta_std = np.std(delta[i, :, :, :, 0].numpy().flatten())
            ax_delta.imshow(delta[i, :, :, 64, 0], vmin=-sigmas*delta_std, vmax=sigmas*delta_std)
            ax_delta.set_title("Delta IC ID={0}".format(IC))
            ax_vbv = fig.add_subplot(gs[i+1,5])
            vbv_std = np.std(vbv_standardized[i, :, :, :, 0].numpy().flatten())
            ax_vbv.imshow(vbv_standardized[i, :, :, 64, 0], vmin=-sigmas*vbv_std, vmax=sigmas*vbv_std)
            ax_vbv.set_title("Vbv IC ID={0}".format(IC))
        else: #histogram delta and vbv_standardised
            ax_delta = fig.add_subplot(gs[i+1,4])
            ax_delta.hist(delta[i, :, :, :, 0].numpy().flatten(), bins=100, alpha=0.5, label="delta", density=True)
            ax_delta.set_title("Histogram delta IC ID={0}".format(IC))
            ax_delta.legend()
            ax_vbv = fig.add_subplot(gs[i+1,5])
            ax_vbv.hist(vbv_standardized[i, :, :, :, 0].numpy().flatten(), bins=100, alpha=0.5, label="vbv", density=True)
            ax_vbv.set_title("Histogram vbv IC ID={0}".format(IC))
            ax_vbv.legend()

    # Save figure
    plt.savefig(model_path+"/loss_history_and_validation_lambda_{0}_lr_{1}.png".format(lbda, learning_rate))

##check T21_lr
#load data
Data = DataManager(path, redshifts=[10,], IC_seeds=list(range(1000,1010)))
T21, delta, vbv, T21_lr = Data.data(augment=False, augments=24, low_res=True)



n_critic = 10
epochs = 200
beta_1 = 0.5
beta_2 = 0.999
learning_rate= np.logspace(-6,-6,1) #np.logspace(-6,-5,2) #np.logspace(-4,-1,4) #1e-4
lbda= np.logspace(1,1,1) #np.logspace(0,0,1) #np.logspace(-4,0,5) #1e-2



combinations = list(itertools.product(lbda, learning_rate))
lbda,learning_rate = combinations[index]

print("Params: ", lbda, learning_rate, flush=True)


generator = Generator()
critic = Critic(lbda=lbda)



generator_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1, beta_2=beta_2)
critic_optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate, beta_1=beta_1, beta_2=beta_2)

#model.summary()
#tf.keras.utils.plot_model(model, to_file=path+'/generator_model.png', show_shapes=True, show_layer_names=True, show_layer_activations=True)




###Test Generator methods:
###generator.build_generator_model and call
#print(generator(test[0:2,:,:,:,10:11], delta[0:2,:,:,:,0:1], vbv[0:2,:,:,:,0:1]).shape) #passed
###generator.generator_loss
#print("gen loss", generator.generator_loss(T21_target[0:2,:,:,:,10:11], delta[0:2,:,:,:,0:1], vbv[0:2,:,:,:,0:1], generator(test[0:2,:,:,:,10:11], delta[0:2,:,:,:,0:1], vbv[0:2,:,:,:,0:1]) , critic)) #passed
###generator.train_step_generator
#print(generator.train_step_generator(test[0:2,:,:,:,10:11], T21_target[0:2,:,:,:,10:11], delta[0:2,:,:,:,0:1], vbv[0:2,:,:,:,0:1], generator_optimizer, critic) )




###Test Critic methods:
###critic.build_critic_model and call
#print(critic(T21_target[0:2,:,:,:,10:11], delta[0:2,:,:,:,0:1], vbv[0:2,:,:,:,0:1])) #passed
###critic.critic_loss
#print("loss: ", critic.critic_loss(T21_target[0:1,:,:,:,10:11], delta[0:1,:,:,:,0:1], vbv[0:1,:,:,:,0:1], generator(test[0:1,:,:,:,10:11], delta[0:1,:,:,:,0:1], vbv[0:1,:,:,:,0:1]) )) #passed
###critic.train_step_critic
#l,gp = critic.train_step_critic(T21_target[0:1,:,:,:,10:11], delta[0:1,:,:,:,0:1], vbv[0:1,:,:,:,0:1], test[0:1,:,:,:,10:11], critic_optimizer, generator)
#print("train loss: ", l,gp,l-gp )




Data = DataManager(path, redshifts=[10,], IC_seeds=list(range(1000,1008)))
#dataset = tf.data.Dataset.from_generator(Data.generator_func,
#                                         args=(True, 2, True),
#                                         output_signature=(
#                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),  # Modify target_shape
#                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),
#                                             tf.TensorSpec(shape=(128,128,128,1), dtype=tf.float32),
#                                             tf.TensorSpec(shape=(64,64,64,1), dtype=tf.float32)
#                                             ))
dataset = Data.data(augment=True, augments=9, low_res=True)
dataset = tf.data.Dataset.from_tensor_slices(dataset)

batches = dataset.batch(4)

print("Number of batches: ", len(list(batches)), flush=True)






model_path = path+"/trained_models/model_{0}".format(31)#index+20)#22
#make model directory if it doesn't exist:
if os.path.exists(model_path)==False:
    os.mkdir(model_path)
ckpt = tf.train.Checkpoint(generator_model=generator.model, critic_model=critic.model, 
                           generator_optimizer=generator_optimizer, critic_optimizer=critic_optimizer,
                           )
manager = tf.train.CheckpointManager(ckpt, model_path+"/checkpoints", max_to_keep=5)

resume = False

if resume:
    weights_before = generator.model.get_weights()
    ckpt.restore(manager.latest_checkpoint)
    weights_after = generator.model.get_weights()
    are_weights_different = any([not np.array_equal(w1, w2) for w1, w2 in zip(weights_before, weights_after)])
    print("Are weights different after restoring from checkpoint: ", are_weights_different, flush=True)

    if (os.path.exists(model_path+"/losses.pkl")==False) or (os.path.exists(model_path+"/checkpoints")==False) or (are_weights_different==False):
        assert False, "Resume=True: Checkpoints directory or losses file does not exist or weights are unchanged after restoring, cannot resume training."
else:
    print("Initializing from scratch.", flush=True)
    if os.path.exists(model_path+"/losses.pkl") or os.path.exists(model_path+"/checkpoints"):
        assert False, "Resume=False: Loss file or checkpoints directory already exists, exiting..."
    print("Creating loss file...", flush=True)
    with open(model_path+"/losses.pkl", "wb") as f:
        generator_losses_epoch = []
        critic_losses_epoch = []
        gradient_penalty_epoch = []
        pickle.dump((generator_losses_epoch, critic_losses_epoch, gradient_penalty_epoch), f)



print("Starting training...", flush=True)
for e in range(epochs):
    start = time.time()

    generator_losses = []
    critic_losses = []
    gradient_penalty = []
    for i, (T21, delta, vbv, T21_lr) in enumerate(batches):
        #print("shape inputs: ", T21.shape, delta.shape, vbv.shape, T21_lr.shape)
        start_start = time.time()
        T21_standardized = standardize(T21, T21_lr)
        T21_lr_standardized = standardize(T21_lr, T21_lr)
        vbv_standardized = standardize(vbv, vbv)
        
        crit_loss, gp = critic.train_step_critic(T21_standardized, delta, vbv_standardized, T21_lr_standardized, critic_optimizer, generator)
        critic_losses.append(crit_loss)
        gradient_penalty.append(gp)

        if i%n_critic == 0:
            gen_loss = generator.train_step_generator(T21_lr_standardized, T21_standardized, delta, vbv_standardized, generator_optimizer, critic)
            generator_losses.append(gen_loss)
        
        print("Time for batch {0} is {1:.2f} sec".format(i + 1, time.time() - start_start), flush=True)
    
    #save losses
    with open(model_path+"/losses.pkl", "rb") as f: # Open the file in read mode and get data
        generator_losses_epoch, critic_losses_epoch, gradient_penalty_epoch = pickle.load(f)
    # Append the new values to the existing data
    generator_losses_epoch.append(np.mean(generator_losses))
    critic_losses_epoch.append(np.mean(critic_losses))
    gradient_penalty_epoch.append(np.mean(gradient_penalty))
    with open(model_path+"/losses.pkl", "wb") as f: # Open the file in write mode and dump the data
        pickle.dump((generator_losses_epoch, critic_losses_epoch, gradient_penalty_epoch), f)
    
    #checkpoint
    #if e%2 == 0:
    print("Saving checkpoint...", flush=True)
    manager.save()
    print("Checkpoint saved!", flush=True)

    #"validation: plot and savefig loss history, and histograms and imshows for two models for every 10th epoch"
    #with gridspec loss history should extend the whole top row and the histograms and imshows should fill one axes[i,j] for the bottom rows
    if e%1 == 0:
        plot_and_save(IC_seeds=[1008,1009,1010], redshift=10, sigmas=3, plot_slice=False)

    print("Time for epoch {0} is {1:.2f} sec \nGenerator mean loss: {2:.2f}, \nCritic mean loss: {3:.2f}, \nGradient mean penalty: {4:.2f}".format(e + 1, time.time() - start, np.mean(generator_losses), np.mean(critic_losses), np.mean(gradient_penalty)), flush=True)
    #break



with open(model_path+"/losses.pkl", "rb") as f:
    generator_losses_epoch, critic_losses_epoch, gradient_penalty_epoch = pickle.load(f)
#print last 10 losses and total number of epochs
print("Last 10 losses: \nGenerator: {0} \nCritic: {1} \nGradient penalty: {2}".format(generator_losses_epoch[-10:], critic_losses_epoch[-10:], gradient_penalty_epoch[-10:]))

"""


#animation

#T21_train = tf.expand_dims(input=tf.cast(T21_train,dtype=tf.float32), axis=0)
#T21_target = tf.expand_dims(input=tf.cast(T21_target,dtype=tf.float32), axis=0)


for e in range(epochs):
    for t in range(n_critic):
        # Select a random batch of big boxes
        indices = np.random.choice(T21_target.shape[0], size=batch_size, replace=False)
        print("batch, target shape 0, indices: ", batch_size, T21_target.shape[0], indices)
        
        T21_big_batch = tf.gather(T21_target, indices, axis=0)#T21_target[indices,:,:,:,:] #10th redshift slice chosen earlier
        IC_delta_batch = tf.gather(delta, indices, axis=0) #delta[indices,:,:,:,:]
        IC_vbv_batch = tf.gather(vbv, indices, axis=0) #vbv[indices,:,:,:,:]

        # Select a random batch of small boxes
        indices = np.random.choice(T21_train.shape[0], size=batch_size, replace=False)
        T21_small_batch = tf.gather(T21_train, indices, axis=0) #T21_train[indices,:,:,:,:] #10th redshift slice chosen earlier
        
        print("shape inputs: ", T21_big_batch.shape, IC_delta_batch.shape, IC_vbv_batch.shape, T21_small_batch.shape)

        # Train the critic network on the batch of big boxes
        critic_loss_value = critic_train_step(T21_big_batch, IC_delta_batch, IC_vbv_batch, T21_small_batch)

    # Select a random batch of small boxes
    indices = np.random.choice(T21_train.shape[0], size=batch_size, replace=False)
    T21_small_batch = tf.gather(T21_train, indices, axis=0)# T21_train[indices,:,:,:,:] #10th redshift slice chosen earlier
    IC_delta_batch = tf.gather(delta, indices, axis=0) #delta[indices,:,:,:,:]
    IC_vbv_batch = tf.gather(vbv, indices, axis=0) #vbv[indices,:,:,:,:]

    # Train the generator network on the batch of small boxes
    generator_loss_value = generator_train_step(T21_small_batch, IC_delta_batch, IC_vbv_batch)
    if e%10000 == 0:
        batch_size *= 2
    # Print the loss values for the critic and generator networks
    print("Epoch: {}, Critic loss: {}, Generator loss: {}".format(e+1, critic_loss_value, generator_loss_value))




    

z = np.arange(6,29,1)[::-1]
Data = DataManager(path, redshifts=list(z[::-1]), IC_seeds=list(range(1000,1002)))
T21, delta, vbv, T21_lr = Data.data(augment=True, augments=2, low_res=True)


# Plotting

if False:

    #fig,ax = plt.subplots(1,2,figsize=(10,5))
    shapes = (2,3)
    fig,ax = plt.subplots(*shapes,figsize=(15,5))
    
    for i in range(T21_lr.shape[0]):
        ind = np.unravel_index(i, shapes)
        #ax[ind].imshow(T21_target[i,:,:,10,-1])
        data_standardized = standardize(T21_lr[i:i+1,:,:,:,-1], T21_lr[i:i+1,:,:,:,-1], i)
        ax[ind].hist(data_standardized[:,:,:,10].numpy().flatten(), bins=100)
    
    def update(i):
        print("z: ", z[i], i)
        for j in range(T21_lr.shape[0]):
            ind = np.unravel_index(j, shapes)
            #ax[ind].imshow(T21_target[j,:,:,10,-i-1])
            #ax[ind].imshow(test[j,:,:,10,-i-1])
            data_standardized = standardize(T21_lr[j:j+1,:,:,:,-i-1], T21_lr[j:j+1,:,:,:,-i-1],j)
            
            try:
                ax[ind].hist(data_standardized[:,:,:,10].numpy().flatten(), bins=100)
            except Exception as e:
                print("couldn't plot j={0}, i={1}, error: ".format(j,i), e)
            #ax[ind].set_title('z = '+str(z[-i-1]))
            #ax[1].imshow(T21_train[3,:,:,10,-i-1])
            #ax.set_axis_off()
            ax[ind].set_xlim(-5,5)
            ax[ind].set_title('z = '+str(z[i]))
        #ax[0].imshow(T21_target[3,:,:,10,-i-1])
        #ax[1].imshow(T21_train[3,:,:,10,-i-1])
        #ax.set_axis_off()

    anim = FuncAnimation(fig, update, frames=z.size, interval=800)

    #fig,axes = plt.subplots(1,3,figsize=(15,5))
    #slice_id = 10

    #im0 = axes[0].imshow(vbv[:,:,slice_id], animated=True)
    #im1 = axes[1].imshow(delta[:,:,slice_id], animated=True)
    #im2 = axes[2].imshow(T21_target[:,:,slice_id,-1], animated=True)

    # Define the animation function
    #def update(i):
    #    axes[2].set_title('z = '+str(z[-i-1]))
    #    axes[2].imshow(T21_target[:,:,slice_id,-i-1])
    #    #ax.set_axis_off()

    #anim = FuncAnimation(fig, update, frames=len(z), interval=800)
    ##plt.show()
    anim.save(path+"/hist_3.gif", dpi=300, writer=PillowWriter(fps=1))

#data_standardized = standardize(T21_lr[j:j+1,:,:,:,-i-1], T21_lr[j:j+1,:,:,:,-i-1])
#check T21_lr if all zeros
#print("tf count nonzero j=0 T21_lr sum: ", tf.math.count_nonzero(T21_lr[0:1,:,:,10,-22-1]))
#mean, var = tf.nn.moments(T21_lr[0:5,:,:,:,-22-1], axes=[1,2,3])

#set mean[i] to 0 and var[i] to 1 if both are zero:


#plt.imshow(T21_lr[0,:,:,10,-22-1])

#plt.title("z={0}, Mean: {1:.2f}, Std: {2:.2f}".format(z[22], mean[0], var[0]**0.5))
#plt.show()
"""
