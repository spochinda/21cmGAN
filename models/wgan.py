import tensorflow as tf

class Critic(tf.keras.Model):
    def __init__(self,kernel_sizes=[7,5,3,1],lbda=1e-2, activation='tanh'):
        super(Critic, self).__init__()
        self.kernel_sizes = kernel_sizes
        self.crop = int((max(self.kernel_sizes)-1))
        self.lbda = lbda
        self.activation = activation
        self.build_critic_model()

    def build_critic_model(self):
        conv1 = tf.keras.layers.Conv3D(filters=8, kernel_size=(self.kernel_sizes[0], self.kernel_sizes[0], self.kernel_sizes[0]), 
                                            kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                            bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                            strides=(2, 2, 2), padding='valid', data_format="channels_last", 
                                            activation=tf.keras.layers.Activation(self.activation)#tf.keras.layers.LeakyReLU(alpha=0.1)
                                            )
        
        conv2 = tf.keras.layers.Conv3D(filters=16, kernel_size=(self.kernel_sizes[1], self.kernel_sizes[1], self.kernel_sizes[1]), 
                                            kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                            bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                            strides=(1, 1, 1), padding='valid', data_format="channels_last", 
                                            activation=tf.keras.layers.Activation(self.activation)#tf.keras.layers.LeakyReLU(alpha=0.1)
                                            )
        
        conv3 = tf.keras.layers.Conv3D(filters=32, kernel_size=(self.kernel_sizes[2], self.kernel_sizes[2], self.kernel_sizes[2]), 
                                            kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                            bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                            strides=(2, 2, 2), padding='valid', data_format="channels_last", 
                                            activation=tf.keras.layers.Activation(self.activation)#tf.keras.layers.LeakyReLU(alpha=0.1)
                                            )
        
        conv4 = tf.keras.layers.Conv3D(filters=64, kernel_size=(self.kernel_sizes[3], self.kernel_sizes[3], self.kernel_sizes[3]), 
                                            kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                            bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                            strides=(1, 1, 1), padding='valid', data_format="channels_last", 
                                            activation=tf.keras.layers.Activation(self.activation)#tf.keras.layers.LeakyReLU(alpha=0.1)
                                            )
        flatten = tf.keras.layers.Flatten()
        out = tf.keras.layers.Dense(units=1,
                                         kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                         bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                         name='output_layer')

        self.model = tf.keras.Sequential([conv1, conv2, conv3, conv4, flatten, out])    
        return self.model

    @tf.function
    def critic_loss(self, T21_big, IC_delta, IC_vbv, generated_boxes):
        #wasserstein loss
        # Generate a batch of fake big boxes using the generator network
        T21_big = tf.keras.layers.Cropping3D(cropping=(self.crop,self.crop,self.crop),data_format="channels_last")(T21_big)
        IC_delta = tf.keras.layers.Cropping3D(cropping=(self.crop,self.crop,self.crop),data_format="channels_last")(IC_delta)
        IC_vbv = tf.keras.layers.Cropping3D(cropping=(self.crop,self.crop,self.crop),data_format="channels_last")(IC_vbv)

        # Evaluate the critic network on the real big boxes and the fake big boxes
        W_real = self.call(T21_big, IC_delta, IC_vbv)
        W_gen = self.call(generated_boxes, IC_delta, IC_vbv)

        epsilon = tf.random.uniform(shape=[T21_big.shape[0], 1, 1, 1, 1], minval=0., maxval=1., seed=None)
        # Compute the interpolated difference between the real and generated samples
        xhat = epsilon * T21_big + (1 - epsilon) * generated_boxes

        # Compute the gradients of the critic network with respect to the interpolated difference
        with tf.GradientTape() as tape:    
            tape.watch(xhat)
            critic_output = self.call(xhat, IC_delta, IC_vbv)
        gradients = tape.gradient(critic_output, xhat)
        l2_norm = tf.math.reduce_euclidean_norm(gradients, axis=[1,2,3])
        gp = self.lbda * tf.square(l2_norm - 1)
        
        #plotting: need to remove tf.function decorator to plot histograms and imshows (e is epoch and i is batch number)
        if False:
            if (e==0) and (i<1):
                fig,axes = plt.subplots(3,4,figsize=(15,5))
                if True:
                    for j in range(2):
                        density = True
                        axes[0,j].hist(T21_big[j,:,:,:,0].numpy().flatten(), density=density, bins=100, alpha=0.5, label="real")
                        axes[1,j].hist(generated_boxes[j,:,:,:,0].numpy().flatten(), density=density, bins=100, alpha=0.5, label="fake")
                        axes[2,j].hist(xhat[j,:,:,:,0].numpy().flatten(), density=density, bins=100, alpha=0.5, label="interpolated")
                        
                        axes[0,j+2].imshow(T21_big[j,:,:,10,0], vmin=-0.5, vmax=0.5)
                        axes[1,j+2].imshow(generated_boxes[j,:,:,10,0], vmin=-0.5, vmax=0.5)
                        axes[2,j+2].imshow(xhat[j,:,:,10,0], vmin=-0.5, vmax=0.5)
                    
                    for j in range(3):
                        for k in range(2):
                            axes[j,k].set_xlim(-5,5)
                            axes[j,k].legend()
                plt.show() 

        # Compute the approximate Wasserstein loss
        #print("W_real={0:.2f} shape={1}, \nW_gen={2:.2f} shape={3}, \ngp={4:.2f} shape={5}".format(tf.reduce_mean(W_real), W_real.shape, tf.reduce_mean(W_gen), W_gen.shape, tf.reduce_mean(gp), gp.shape))
        loss = tf.reduce_mean(W_gen - W_real + gp)

        return loss, gp 

    @tf.function
    def train_step_critic(self, T21_big, IC_delta, IC_vbv, T21_small, optimizer, generator):
        #
        #Function that performs one training step for the critic network.
        #The function calls the loss function for the critic network, computes the gradients,
        #and applies the gradients to the network's parameters.
        #

        with tf.GradientTape() as disc_tape:
            generated_boxes = generator(T21_small, IC_delta, IC_vbv)
            crit_loss, gp = self.critic_loss(T21_big, IC_delta, IC_vbv, generated_boxes)

        grad_disc = disc_tape.gradient(crit_loss, self.model.trainable_variables)
        optimizer.apply_gradients(zip(grad_disc, self.model.trainable_variables))
        
        return crit_loss, gp
    
    @tf.function
    def call(self, T21_target, IC_delta, IC_vbv):
        data_target = tf.concat((T21_target, IC_delta, IC_vbv), axis=4)
        x_out_model = self.model(data_target)
        return x_out_model

class InceptionLayer(tf.keras.layers.Layer):
    def __init__(self, input_channels=1, filters_1x1x1_7x7x7=6, filters_7x7x7=6, filters_1x1x1_5x5x5=6, filters_5x5x5=6, filters_1x1x1_3x3x3=6, filters_3x3x3=6, filters_1x1x1=6):
        super(InceptionLayer, self).__init__()
        self.input_channels = input_channels
        self.conv_1x1x1_7x7x7 = tf.keras.layers.Conv3D(filters=filters_1x1x1_7x7x7, kernel_size=(1, 1, 1),
                                                       kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                       bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                       strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                       activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                       )
        self.conv_7x7x7 = tf.keras.layers.Conv3D(filters=filters_7x7x7, kernel_size=(7, 7, 7),
                                                 kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                 bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                 strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                 activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                 )
        self.conv_1x1x1_5x5x5 = tf.keras.layers.Conv3D(filters=filters_1x1x1_5x5x5, kernel_size=(1, 1, 1),
                                                            kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                            bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                            strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                            activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                            )
        self.conv_5x5x5 = tf.keras.layers.Conv3D(filters=filters_5x5x5, kernel_size=(5, 5, 5),
                                                 kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                 bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                 strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                 activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                 )
        self.crop_5x5x5 = tf.keras.layers.Cropping3D(cropping=(1, 1, 1),data_format="channels_last")

        self.conv_1x1x1_3x3x3 = tf.keras.layers.Conv3D(filters=filters_1x1x1_3x3x3, kernel_size=(1, 1, 1),
                                                       kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                       bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                       strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                       activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                       )
        self.conv_3x3x3 = tf.keras.layers.Conv3D(filters=filters_3x3x3, kernel_size=(3, 3, 3),
                                                 kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                 bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                 strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                 activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                 )
        self.crop_3x3x3 = tf.keras.layers.Cropping3D(cropping=(2, 2, 2),data_format="channels_last")
        
        self.conv_1x1x1 = tf.keras.layers.Conv3D(filters=filters_1x1x1, kernel_size=(1, 1, 1),
                                                 kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                 bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                 strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                 activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                 )
        
        self.crop_1x1x1 = tf.keras.layers.Cropping3D(cropping=(3, 3, 3),data_format="channels_last")
        self.concat = tf.keras.layers.Concatenate(axis=4)#([x1, x2, x3, x4])
        
        self.crop_x = tf.keras.layers.Cropping3D(cropping=(3, 3, 3),data_format="channels_last")#(x[:,:,:,:,0:1])
        #self.tile_x = tf.keras.layers.Lambda(lambda x: tf.tile(x, [1, 1, 1, 1, x_out.shape[-1]]))(x_out_)

        self.conv_1x1x1_reduce_channels = tf.keras.layers.Conv3D(filters=filters_7x7x7+filters_5x5x5+filters_3x3x3+filters_1x1x1, kernel_size=(1, 1, 1), #warning: number of filters not generalized
                                                 kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                                 bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                                 strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                                 activation=None #tf.keras.layers.LeakyReLU(alpha=0.1)
                                                 )

    def call(self, x):
        x1 = self.conv_1x1x1_7x7x7(x)
        x1 = self.conv_7x7x7(x1)
        
        x2 = self.conv_1x1x1_5x5x5(x)
        x2 = self.conv_5x5x5(x2)
        x2 = self.crop_5x5x5(x2)
        
        x3 = self.conv_1x1x1_3x3x3(x)
        x3 = self.conv_3x3x3(x3)
        x3 = self.crop_3x3x3(x3)
        
        x4 = self.conv_1x1x1(x)
        x4 = self.crop_1x1x1(x4)
        x_out = self.concat([x1, x2, x3, x4])
        x_out_ = self.crop_x(x[:,:,:,:,:])#crop input to right size, x[:,:,:,:,0:1] but not sure if this is the right way to do it
        #the issue is that the number of channels at the second pass through the inception
        #block is larger for the input than the output, so during the add step
        #I can't tile the input to match the output because it is larger.
        #Might have to implement change the number of filters to match the input 
        #on the second pass through, or do a 1x1x1 pointwise convolution to 
        #effectively reduce the number of channels to match the output. 
        #The 1x1x1 convolution is basically a weighted average of channels,
        # or linear transformation, with learned weights.
        #Update: implemented 1x1x1 convolution to reduce number of channels
        if self.input_channels > x_out.shape[-1]:
            x_out_ = self.conv_1x1x1_reduce_channels(x_out_)
        else:
            x_out_ = tf.keras.layers.Lambda(lambda x: tf.tile(x, [1, 1, 1, 1, x_out.shape[-1]]))(x_out_)
        return tf.add(x_out, x_out_)



class Generator(tf.keras.Model):
    def __init__(self, T21_shape=(1,64,64,64,1), delta_shape=(1,128,128,128,1), vbv_shape=(1,128,128,128,1),
                 activation='tanh'):
        super(Generator, self).__init__()
        self.T21_shape = T21_shape
        self.delta_shape = delta_shape
        self.vbv_shape = vbv_shape
        self.upsampling = int(delta_shape[1]/T21_shape[1])
        self.activation = activation
        self.build_generator_model()

    def build_generator_model(self):
        inputs_T21 = tf.keras.layers.Input(shape=self.T21_shape[1:]) #not including the batch size according to docs
        inputs_delta = tf.keras.layers.Input(shape=self.delta_shape[1:])
        inputs_vbv = tf.keras.layers.Input(shape=self.vbv_shape[1:])

        T21 = tf.keras.layers.UpSampling3D(size=self.upsampling, data_format="channels_last")(inputs_T21)
        T21 = InceptionLayer(input_channels=inputs_T21.shape[-1])(T21) #tf.keras.layers.Lambda(self.inception__)(T21) #self.inception__(T21)
        #change to tanh activation#T21 = tf.keras.layers.LeakyReLU(alpha=0.1)(T21) #nn.leaky_relu(T21, 0.1)
        T21 = tf.keras.layers.Activation(self.activation)(T21)
        
        delta = InceptionLayer(input_channels=inputs_delta.shape[-1])(inputs_delta) #tf.keras.layers.Lambda(self.inception__)(inputs_delta) #self.inception__(inputs_delta)
        delta = tf.keras.layers.LeakyReLU(alpha=0.1)(delta) #tf.nn.leaky_relu(delta, 0.1)

        vbv = InceptionLayer(input_channels=inputs_vbv.shape[-1])(inputs_vbv) #tf.keras.layers.Lambda(self.inception__)(inputs_vbv)
        vbv = tf.keras.layers.Activation(self.activation)(vbv) #tf.keras.layers.LeakyReLU(alpha=0.1)(vbv) #tf.nn.leaky_relu(vbv, 0.1)

        data = tf.keras.layers.Concatenate(axis=4)([T21, delta, vbv])
        
        data = InceptionLayer(input_channels=data.shape[-1])(data) #tf.keras.layers.Lambda(self.inception__)(data)
        data = tf.keras.layers.Activation(self.activation)(data)#tf.keras.layers.LeakyReLU(alpha=0.1)(data) #tf.nn.leaky_relu(data, 0.1)
        data = tf.keras.layers.Conv3D(filters=1,#data.shape[-1], 
                                      kernel_size=(1, 1, 1),
                                      kernel_initializer=tf.keras.initializers.RandomNormal(mean=0.0, stddev=0.1, seed=None),
                                      bias_initializer=tf.keras.initializers.Constant(value=0.1),
                                      strides=(1, 1, 1), padding='valid', data_format="channels_last",
                                      activation=tf.keras.layers.Activation(self.activation)#tf.keras.layers.LeakyReLU(alpha=0.1)
                                      )(data)
        #data = tf.keras.layers.ReLU()(data) 
        
        self.model = tf.keras.Model(inputs=[inputs_T21, inputs_delta, inputs_vbv], outputs=data)
        return self.model

    @tf.function
    def generator_loss(self, T21_big, IC_delta, IC_vbv, generated_boxes, critic):
        T21_big = tf.keras.layers.Cropping3D(cropping=(6, 6, 6),data_format="channels_last")(T21_big)
        IC_delta = tf.keras.layers.Cropping3D(cropping=(6, 6, 6),data_format="channels_last")(IC_delta)
        IC_vbv = tf.keras.layers.Cropping3D(cropping=(6, 6, 6),data_format="channels_last")(IC_vbv)
        
        #W_real = critic(T21_big, IC_delta, IC_vbv)
        W_gen = critic(generated_boxes, IC_delta, IC_vbv)

        loss = - tf.reduce_mean(W_gen) #- tf.reduce_mean(W_real - W_gen)
        return loss

    @tf.function
    def train_step_generator(self, T21_small, T21_big, IC_delta, IC_vbv, optimizer, critic):
        #
        #Function that performs one training step for the generator network.
        #The function calls the loss function for the generator network, computes the gradients,
        #and applies the gradients to the network's parameters.
        #

        with tf.GradientTape() as gen_tape: 
            generated_boxes = self.call(T21_small, IC_delta, IC_vbv)
            #generated_output = Critic(generated_boxes, IC_delta, IC_vbv)
            gen_loss = self.generator_loss(T21_big, IC_delta, IC_vbv, generated_boxes, critic)

        grad_gen = gen_tape.gradient(gen_loss, self.model.trainable_variables)
        optimizer.apply_gradients(zip(grad_gen, self.model.trainable_variables))

        return gen_loss
        
    @tf.function    
    def call(self, T21_train, IC_delta, IC_vbv):
        return self.model(inputs=[T21_train, IC_delta, IC_vbv])