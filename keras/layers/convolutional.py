# -*- coding: utf-8 -*-
from __future__ import absolute_import
import functools

from .. import backend as K
from .. import activations
from .. import initializations
from .. import regularizers
from .. import constraints
from ..engine import Layer
from ..engine import InputSpec
from ..utils.np_utils import conv_output_length
from ..utils.np_utils import conv_input_length

# imports for backwards namespace compatibility
from .pooling import AveragePooling1D
from .pooling import AveragePooling2D
from .pooling import AveragePooling3D
from .pooling import MaxPooling1D
from .pooling import MaxPooling2D
from .pooling import MaxPooling3D


class Convolution1D(Layer):
    """Convolution operator for filtering neighborhoods of 1-D inputs.

    When using this layer as the first layer in a model,
    either provide the keyword argument `input_dim`
    (int, e.g. 128 for sequences of 128-dimensional vectors),
    or `input_shape` (tuple of integers, e.g. (10, 128) for sequences
    of 10 vectors of 128-dimensional vectors).

    # Example

    ```python
        # apply a convolution 1d of length 3 to a sequence with 10 timesteps,
        # with 64 output filters
        model = Sequential()
        model.add(Convolution1D(64, 3, border_mode='same', input_shape=(10, 32)))
        # now model.output_shape == (None, 10, 64)

        # add a new conv1d on top
        model.add(Convolution1D(32, 3, border_mode='same'))
        # now model.output_shape == (None, 10, 32)
    ```

    # Arguments
        nb_filter: Number of convolution kernels to use
            (dimensionality of the output).
        filter_length: The extension (spatial or temporal) of each filter.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant
            if you don't pass a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample_length: factor by which to subsample output.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).
        input_dim: Number of channels/dimensions in the input.
            Either this argument or the keyword argument `input_shape`must be
            provided when using this layer as the first layer in a model.
        input_length: Length of input sequences, when it is constant.
            This argument is required if you are going to connect
            `Flatten` then `Dense` layers upstream
            (without it, the shape of the dense outputs cannot be computed).

    # Input shape
        3D tensor with shape: `(samples, steps, input_dim)`.

    # Output shape
        3D tensor with shape: `(samples, new_steps, nb_filter)`.
        `steps` value might have changed due to padding.
    """

    def __init__(self, nb_filter, filter_length,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample_length=1,
                 W_regularizer=None, b_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, input_dim=None, input_length=None, **kwargs):

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution1D:', border_mode)
        self.nb_filter = nb_filter
        self.filter_length = filter_length
        self.init = initializations.get(init)
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample_length = subsample_length

        self.subsample = (subsample_length, 1)

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.W_constraint = constraints.get(W_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=3)]
        self.initial_weights = weights
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(Convolution1D, self).__init__(**kwargs)

    def build(self, input_shape):
        input_dim = input_shape[2]
        self.W_shape = (self.filter_length, 1, input_dim, self.nb_filter)

        self.W = self.add_weight(self.W_shape,
                                 initializer=functools.partial(self.init,
                                                               dim_ordering='th'),
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)
        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        length = conv_output_length(input_shape[1],
                                    self.filter_length,
                                    self.border_mode,
                                    self.subsample[0])
        return (input_shape[0], length, self.nb_filter)

    def call(self, x, mask=None):
        x = K.expand_dims(x, 2)  # add a dummy dimension
        output = K.conv2d(x, self.W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering='tf')
        output = K.squeeze(output, 2)  # remove the dummy dimension
        if self.bias:
            output += K.reshape(self.b, (1, 1, self.nb_filter))
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'filter_length': self.filter_length,
                  'init': self.init.__name__,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample_length': self.subsample_length,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'W_constraint': self.W_constraint.get_config() if self.W_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  'bias': self.bias,
                  'input_dim': self.input_dim,
                  'input_length': self.input_length}
        base_config = super(Convolution1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Convolution1DFromWeightFile(Convolution1D):

    def __init__(self, weight_file, **kwargs):
        import numpy as np
        weights = np.load(weight_file)
        nb_filter = weights.shape[-1]
        filter_length = weights.shape[0]
        b = np.zeros((nb_filter,))
        super(Convolution1DFromWeightFile, self).__init__(
            nb_filter=nb_filter, filter_length=filter_length,
            weights=[weights, b], **kwargs
        )


class FullySepConv1D(Convolution1D):

    def __init__(self, nb_filter, filter_length,
                 activation=None, weights=None,
                 border_mode='valid', subsample_length=1,
                 activity_regularizer=None,
                 bias=True, input_dim=None, input_length=None, **kwargs):

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution1D:', border_mode)
        self.nb_filter = nb_filter
        self.filter_length = filter_length
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample_length = subsample_length

        self.subsample = (subsample_length, 1)

        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=3)]
        self.initial_weights = weights
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(Convolution1D, self).__init__(**kwargs)

    def build(self, input_shape):
        import numpy as np

        input_dim = input_shape[2]
        self.W_pos_shape = (self.filter_length, self.nb_filter)
        self.W_chan_shape = (input_dim, self.nb_filter)
 
        self.init = (lambda shape, name: initializations.uniform(
            shape, np.sqrt(
            np.sqrt(2.0/(self.filter_length*(input_dim+self.nb_filter)))),
            name))

        self.W_pos = self.add_weight(self.W_pos_shape,
                                     initializer=self.init,
                                     name='{}_W_pos'.format(self.name))
        self.W_chan = self.add_weight(self.W_chan_shape,
                                     initializer=self.init,
                                     name='{}_W_chan'.format(self.name))

        self.W = (K.expand_dims(K.expand_dims(self.W_pos, 1),1)*
                  K.expand_dims(K.expand_dims(self.W_chan,0),0))

        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name))
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'filter_length': self.filter_length,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample_length': self.subsample_length,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'bias': self.bias,
                  'input_dim': self.input_dim,
                  'input_length': self.input_length}
        base_config = super(Convolution1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class FullySepSplitConv1D(Convolution1D):

    def __init__(self, nb_filter, half_filter_length,
                 activation=None, weights=None,
                 border_mode='valid', subsample_length=1,
                 activity_regularizer=None,
                 bias=True, input_dim=None, input_length=None, **kwargs):

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution1D:', border_mode)
        self.nb_filter = nb_filter
        self.half_filter_length = half_filter_length
        self.filter_length = 2*half_filter_length
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample_length = subsample_length

        self.subsample = (subsample_length, 1)

        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=3)]
        self.initial_weights = weights
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(Convolution1D, self).__init__(**kwargs)

    def build(self, input_shape):
        import numpy as np

        input_dim = input_shape[2]
        self.W_pos_shape = (self.half_filter_length, self.nb_filter)
        self.W_chan_shape = (input_dim, self.nb_filter)
 
        self.init = (lambda shape, name: initializations.uniform(
            shape, np.sqrt(
            np.sqrt(2.0/(self.filter_length*(input_dim+self.nb_filter)))),
            name))

        self.W_pos_left = self.add_weight(self.W_pos_shape,
                                     initializer=self.init,
                                     name='{}_W_pos_left'.format(self.name))
        self.W_pos_right = self.add_weight(self.W_pos_shape,
                                     initializer=self.init,
                                     name='{}_W_pos_right'.format(self.name))
        self.W_chan_left = self.add_weight(self.W_chan_shape,
                                     initializer=self.init,
                                     name='{}_W_chan_left'.format(self.name))
        self.W_chan_right = self.add_weight(self.W_chan_shape,
                                     initializer=self.init,
                                     name='{}_W_chan_right'.format(self.name))

        self.W = K.concatenate(
                  [(K.expand_dims(K.expand_dims(self.W_pos_left, 1),1)*
                    K.expand_dims(K.expand_dims(self.W_chan_left,0),0)),
                   (K.expand_dims(K.expand_dims(self.W_pos_right, 1),1)*
                    K.expand_dims(K.expand_dims(self.W_chan_right,0),0))],
                  axis=0)

        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name))
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'half_filter_length': self.half_filter_length,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample_length': self.subsample_length,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'bias': self.bias,
                  'input_dim': self.input_dim,
                  'input_length': self.input_length}
        base_config = super(Convolution1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class GappyConv1D(Layer):

    def __init__(self, nb_filter, half_filter_length, min_gap, max_gap,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample_length=1,
                 W_regularizer=None, b_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, input_dim=None, input_length=None, **kwargs):

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution1D:', border_mode)
        self.nb_filter = nb_filter
        self.half_filter_length = half_filter_length
        self.min_gap = min_gap
        self.max_gap = max_gap
        self.num_gaps = ((self.max_gap-self.min_gap)+1)
        self.init = initializations.get(init)
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample_length = subsample_length

        self.subsample = (subsample_length, 1)

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.W_constraint = constraints.get(W_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=3)]
        self.initial_weights = weights
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(GappyConv1D, self).__init__(**kwargs)

    def build(self, input_shape):
        input_dim = input_shape[2]
        #I use self.output_length in the call function
        self.output_length = conv_output_length(input_shape[1],
                                    2*self.half_filter_length+self.max_gap,
                                    self.border_mode,
                                    self.subsample[0])

        self.W_shape = (2*self.half_filter_length, 1,
                        input_dim, self.nb_filter)

        self.W = self.add_weight(self.W_shape,
                                 initializer=functools.partial(self.init,
                                                               dim_ordering='th'),
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)

        W_left = self.W[:self.half_filter_length, :, :, :]
        W_right = self.W[self.half_filter_length:, :, :, :]

        #build up the final W where all the different gap sizes are
        #represented
        Ws_to_stitch = []
        import numpy as np
        for gap_size in range(self.min_gap, self.max_gap+1):
            flank_size = self.max_gap-gap_size
            left_flank_size = int(flank_size/2)
            right_flank_size = flank_size-left_flank_size
            #K.zeros is less than ideal as it makes a shared variable
            left_flank_zeros = K.zeros((left_flank_size, 1,
                          input_dim, self.nb_filter))
            right_flank_zeros = K.zeros((right_flank_size, 1,
                          input_dim, self.nb_filter))
            central_zeros = K.zeros((gap_size, 1,
                          input_dim, self.nb_filter))
            Ws_to_stitch.append(K.concatenate([left_flank_zeros, W_left,
                                         central_zeros, W_right,
                                         right_flank_zeros], axis=0)) 
        #stich the spaced Ws along the filter axis
        self.final_W = K.concatenate(Ws_to_stitch, axis=-1)

        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        length = conv_output_length(input_shape[1],
                                    2*self.half_filter_length+self.max_gap,
                                    self.border_mode,
                                    self.subsample[0])
        return (input_shape[0], length, self.num_gaps, self.nb_filter)

    def call(self, x, mask=None):
        x = K.expand_dims(x, 2)  # add a dummy dimension
        #scan using a weight matrix that has all the different
        #gap sizes represented
        with_gaps_output = K.conv2d(x, self.final_W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering='tf')
        with_gaps_output = K.squeeze(with_gaps_output, 2)  # remove dummy dim
        #with_gaps_output is samples x length x (num_gaps*num_filters)
        #reshape to samples x length x num_gaps x num_filters
        reshape_with_gaps_output = K.reshape(
            with_gaps_output, (-1, self.output_length, 
                               self.num_gaps, self.nb_filter))
        if (self.bias):
            reshape_with_gaps_output += K.reshape(
                                         self.b, (1, 1, 1, self.nb_filter))
        reshape_with_gaps_output = self.activation(reshape_with_gaps_output)
        return reshape_with_gaps_output

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'half_filter_length': self.half_filter_length,
                  'min_gap': self.min_gap,
                  'max_gap': self.max_gap,
                  'init': self.init.__name__,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample_length': self.subsample_length,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'W_constraint': self.W_constraint.get_config() if self.W_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  'bias': self.bias,
                  'input_dim': self.input_dim,
                  'input_length': self.input_length}
        base_config = super(GappyConv1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class MaxForGappyConv1D(Layer):

    def get_output_shape_for(self, input_shape):
        return (input_shape[0], input_shape[1], input_shape[3])

    def call(self, x, mask=None):
        return K.max(x,axis=2)


class WeightedSumForGappyConv1D(Layer):

    def __init__(self, weights=None,
                 W_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None,
                 **kwargs):

        self.W_regularizer = regularizers.get(W_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)
        self.W_constraint = constraints.get(W_constraint)
        self.input_spec = [InputSpec(ndim=4)]
        self.initial_weights = weights
        super(WeightedSumForGappyConv1D, self).__init__(**kwargs)

    def build(self, input_shape):
        assert len(input_shape)==4
        self.num_gaps = input_shape[2]
        self.nb_filter = input_shape[3]
        self.W_shape = (self.num_gaps, self.nb_filter)
        self.W = self.add_weight(self.W_shape,
                                 initializer=functools.partial(
                                    initializations.get("one"),
                                    dim_ordering='th'),
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        return (input_shape[0], input_shape[1], input_shape[3])

    def call(self, x, mask=None):
        return K.mean(K.expand_dims(K.expand_dims(self.W,0),0)*x,axis=2)

    def get_config(self):
        config = {'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'W_constraint': self.W_constraint.get_config() if self.W_constraint else None}
        base_config = super(WeightedSumForGappyConv1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Compute1DReverseComplement(Layer):
    '''Reverses the length and channel dimensions of its input. No parameters.

    # Arguments
        input_dim: Number of channels/dimensions in the input.
            Either this argument or the keyword argument `input_shape`must be
            provided when using this layer as the first layer in a model.
        input_length: Length of input sequences, when it is constant.
            This argument is required if you are going to connect
            `Flatten` then `Dense` layers upstream
            (without it, the shape of the dense outputs cannot be computed).

    # Input shape
        3D tensor with shape: `(samples, steps, input_dim)`.

    # Output shape
        3D tensor with shape: `(samples, steps, input_dim)`.
    '''
    def __init__(self, input_dim=None, input_length=None, **kwargs):
        self.input_dim = input_dim
        self.input_length = input_length
        if self.input_dim:
            kwargs['input_shape'] = (self.input_length, self.input_dim)
        super(Compute1DReverseComplement, self).__init__(**kwargs)

    def build(self, input_shape):
        #no weights; nothing to build
        self.built = True

    def get_output_shape_for(self, input_shape):
        return (input_shape[0], input_shape[1], input_shape[2])

    def call(self, x, mask=None):
        return x[:, ::-1, ::-1]

    def get_config(self):
        config = {'input_dim': self.input_dim,
                  'input_length': self.input_length}
        base_config = super(Compute1DReverseComplement, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class RevCompConv1D(Convolution1D):
    '''Like Convolution1D, except the reverse-complement filters with tied
    weights are added in the channel dimension. The reverse complement
    of the channel at index i is at index -i.

    # Example

    ```python
        # apply a reverse-complemented convolution 1d of length 20
        # to a sequence with 100bp input, with 2*64 output filters
        model = Sequential()
        model.add(RevCompConv1D(nb_filter=64, filter_length=20,
                                border_mode='same', input_shape=(100, 4)))
        # now model.output_shape == (None, 100, 128)

        # add a new reverse-complemented conv1d on top
        model.add(RevCompConv1D(nb_filter=32, filter_length=10,
                                border_mode='same'))
        # now model.output_shape == (None, 10, 64)
    ```

    # Arguments
        nb_filter: Number of non-reverse complemented convolution kernels
            to use (half the dimensionality of the output).
        filter_length: The extension (spatial or temporal) of each filter.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)),
            or alternatively, Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights
            (reverse-complemented portion should not be included as 
            it's applied during compilation)
        border_mode: 'valid', 'same' or 'full'. ('full' requires the Theano backend.)
        subsample_length: factor by which to subsample output.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).
        input_dim: Number of channels/dimensions in the input.
            Either this argument or the keyword argument `input_shape`must be
            provided when using this layer as the first layer in a model.
        input_length: Length of input sequences, when it is constant.
            This argument is required if you are going to connect
            `Flatten` then `Dense` layers upstream
            (without it, the shape of the dense outputs cannot be computed).

    # Input shape
        3D tensor with shape: `(samples, steps, input_dim)`.

    # Output shape
        3D tensor with shape: `(samples, new_steps, nb_filter)`.
        `steps` value might have changed due to padding.
    '''

    def get_output_shape_for(self, input_shape):
        length = conv_output_length(input_shape[1],
                                    self.filter_length,
                                    self.border_mode,
                                    self.subsample[0])
        return (input_shape[0], length, 2*self.nb_filter)

    def call(self, x, mask=None):
        #create a rev-comped W. The last axis is the output channel axis.
        #dim 1 is dummy axis of size 1 (see 'build' method in Convolution1D)
        #Rev comp is along both the length (dim 0) and input channel (dim 2)
        #axes; that is the reason for ::-1, ::-1 in the first and third dims.
        #The rev-comp of channel at index i should be at index -i
        #This is the reason for the ::-1 in the last dim.
        rev_comp_W = K.concatenate([self.W, self.W[::-1,:,::-1,::-1]],axis=-1)
        if (self.bias):
            rev_comp_b = K.concatenate([self.b, self.b[::-1]], axis=-1)
        x = K.expand_dims(x, 2)  # add a dummy dimension
        output = K.conv2d(x, rev_comp_W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering='tf')
        output = K.squeeze(output, 2)  # remove the dummy dimension
        if self.bias:
            output += K.reshape(rev_comp_b, (1, 1, 2*self.nb_filter))
        output = self.activation(output)
        return output


class WeightedSum1D(Layer):
    '''Learns a weight for each position, for each channel, and sums
    lengthwise.

    # Arguments
        symmetric: if want weights to be symmetric along length, set to True
        input_is_revcomp_conv: if the input is [RevCompConv1D], set to True for
            added weight sharing between reverse-complement pairs
        smoothness_penalty: penalty to be applied to absolute difference
            of adjacent weights in the length dimension
        bias: whether or not to have bias parameters
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)),
            or alternatively, Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass a `weights` argument.
        weights: list of numpy arrays to set as initial weights.

    # Input shape
        3D tensor with shape: `(samples, steps, features)`.

    # Output shape
        2D tensor with shape: `(samples, features)`.
    '''
    def __init__(self, symmetric, input_is_revcomp_conv,
                       smoothness_penalty=None, bias=False,
                       init='fanintimesfanouttimestwo', weights=None,
                       **kwargs):
        super(WeightedSum1D, self).__init__(**kwargs)
        self.symmetric = symmetric
        self.input_is_revcomp_conv = input_is_revcomp_conv
        self.smoothness_penalty = smoothness_penalty
        self.bias = bias
        self.initial_weights = weights
        self.input_spec = [InputSpec(ndim=3)]
        self.init = initializations.get(init)

    def build(self, input_shape): 
        #input_shape[0] is the batch index
        #input_shape[1] is length of input
        #input_shape[2] is number of filters

        if (self.symmetric == False):
            W_length = input_shape[1]
        else:
            self.odd_input_length = input_shape[1]%2.0 == 1
            #+0.5 below turns floor into ceil
            W_length = int(input_shape[1]/2.0 + 0.5)

        if (self.input_is_revcomp_conv == False):
            W_chan = input_shape[2]
        else:
            assert input_shape[2]%2==0,\
             "if input is revcomp conv, # incoming channels would be even"
            W_chan = int(input_shape[2]/2)

        self.W_shape = (W_length, W_chan)
        self.b_shape = (W_chan,)
        self.W = self.add_weight(self.W_shape,
             initializer=functools.partial(
              self.init, dim_ordering='th'),
             name='{}_W'.format(self.name),
             regularizer=(None if self.smoothness_penalty is None else
                         regularizers.SmoothnessRegularizer(
                          self.smoothness_penalty)))
        if (self.bias):
            self.b = self.add_weight(self.b_shape,
                 initializer=functools.partial(
                  self.init, dim_ordering='th'),
                 name='{}_b'.format(self.name))

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    #3D input -> 2D output (loses length dimension)
    def get_output_shape_for(self, input_shape):
        return (input_shape[0], input_shape[2])

    def call(self, x, mask=None):
        if (self.symmetric == False):
            W = self.W
        else:
            W = K.concatenate(
                 tensors=[self.W,
                          #reverse along length, concat along length
                          self.W[::-1][(1 if self.odd_input_length else 0):]],
                 axis=0)
        if (self.bias):
            b = self.b
        if (self.input_is_revcomp_conv):
            #reverse along both length and channel dims, concat along chan
            #if symmetric=True, reversal along length here makes no diff
            W = K.concatenate(tensors=[W, W[::-1,::-1]], axis=1)
            if (self.bias):
                b = K.concatenate(tensors=[b, b[::-1]], axis=0)
        output = K.sum(x*K.expand_dims(W,0), axis=1)
        if (self.bias):
            output = output + K.expand_dims(b,0)
        return output 

    def get_config(self):
        config = {'symmetric': self.symmetric,
                  'input_is_revcomp_conv': self.input_is_revcomp_conv,
                  'smoothness_penalty': self.smoothness_penalty,
                  'bias': self.bias,
                  'init': self.init.__name__}
        base_config = super(WeightedSum1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class SeparableFC(Layer):
    '''A Fully-Connected layer with a weights tensor that is
       the product of a matrix W_pos, for learning spatial correlations,
       and a matrix W_chan, for learning cross-channel correlations.
       
    # Arguments
        output_dim: the number of output neurons
        symmetric: if weights are to be symmetric along length, set to True
        smoothness_penalty: penalty to be applied to difference
            of adjacent weights in the length dimensions
        smoothness_l1: if smoothness penalty is to be computed in terms of the
            the absolute difference, set to True
            otherwise, penalty is computed in terms of the squared difference
        smoothness_second_diff: if smoothness penalty is to be applied to the
            difference of the difference, set to True
            otherwise, penalty is applied to the first difference
        curvature_constraint: constraint to be enforced on the second differences
            of the positional weights matrix
            
    # Input shape
        3D tensor with shape: `(samples, steps, features)`.
        
    # Output shape
        2D tensor with shape: `(samples, output_features)`.
    '''
    def __init__(self, output_dim, symmetric,
                       smoothness_penalty = None,
                       smoothness_l1 = False,
                       smoothness_second_diff = True,
                       curvature_constraint = None, **kwargs):
        super(SeparableFC, self).__init__(**kwargs)
        self.output_dim = output_dim
        self.symmetric = symmetric
        self.smoothness_penalty = smoothness_penalty
        self.smoothness_l1 = smoothness_l1
        self.smoothness_second_diff = smoothness_second_diff
        self.curvature_constraint = curvature_constraint

    def build(self, input_shape):
        import numpy as np
        self.original_length = input_shape[1]
        if (self.symmetric == False):
            self.length = input_shape[1]
        else:
            self.odd_input_length = input_shape[1]%2.0 == 1
            self.length = int(input_shape[1]/2.0 + 0.5)
        self.num_channels = input_shape[2]
        self.init = (lambda shape, name: initializations.uniform(
            shape, np.sqrt(
            np.sqrt(2.0/(self.length*self.num_channels+self.output_dim))),
            name))
        self.W_pos = self.add_weight(
            shape = (self.output_dim, self.length),
            name='{}_W_pos'.format(self.name), initializer=self.init,
            constraint=(None if self.curvature_constraint is None else
                constraints.CurvatureConstraint(
                    self.curvature_constraint)),
            regularizer=(None if self.smoothness_penalty is None else
                regularizers.SepFCSmoothnessRegularizer(
                    self.smoothness_penalty,
                    self.smoothness_l1,
                    self.smoothness_second_diff)))
        self.W_chan = self.add_weight(
            shape = (self.output_dim, self.num_channels),
            name='{}_W_chan'.format(self.name), initializer=self.init,
            trainable=True)
        self.built = True

    def get_output_shape_for(self, input_shape):
        return (input_shape[0], self.output_dim)
    
    def call(self, x, mask=None):
        if (self.symmetric == False):
            W_pos = self.W_pos
        else:
            W_pos = K.concatenate(
                tensors=[self.W_pos,
                self.W_pos[:,::-1][:,(1 if self.odd_input_length else 0):]],
                axis=1)
        W_output = K.expand_dims(W_pos, 2) * K.expand_dims(self.W_chan, 1)
        W_output = K.reshape(W_output,
          (self.output_dim, self.original_length*self.num_channels))
        x = K.reshape(x,
          (-1, self.original_length*self.num_channels))
        output = K.dot(x, K.transpose(W_output))
        return output 

    def get_config(self):
        config = {'output_dim': self.output_dim,
                  'symmetric': self.symmetric,
                  'smoothness_penalty': self.smoothness_penalty,
                  'smoothness_l1': self.smoothness_l1,
                  'smoothness_second_diff': self.smoothness_second_diff,
                  'curvature_constraint': self.curvature_constraint}
        base_config = super(SeparableFC, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class AtrousConvolution1D(Convolution1D):
    """Atrous Convolution operator for filtering neighborhoods of 1-D inputs.

    A.k.a dilated convolution or convolution with holes.
    When using this layer as the first layer in a model,
    either provide the keyword argument `input_dim`
    (int, e.g. 128 for sequences of 128-dimensional vectors),
    or `input_shape` (tuples of integers, e.g. (10, 128) for sequences
    of 10 vectors of 128-dimensional vectors).

    # Example

    ```python
        # apply an atrous convolution 1d
        # with atrous rate 2 of length 3 to a sequence with 10 timesteps,
        # with 64 output filters
        model = Sequential()
        model.add(AtrousConvolution1D(64, 3, atrous_rate=2,
                                      border_mode='same',
                                      input_shape=(10, 32)))
        # now model.output_shape == (None, 10, 64)

        # add a new atrous conv1d on top
        model.add(AtrousConvolution1D(32, 3, atrous_rate=2,
                                      border_mode='same'))
        # now model.output_shape == (None, 10, 32)
    ```

    # Arguments
        nb_filter: Number of convolution kernels to use
            (dimensionality of the output).
        filter_length: The extension (spatial or temporal) of each filter.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant
            if you don't pass a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample_length: factor by which to subsample output.
        atrous_rate: Factor for kernel dilation. Also called filter_dilation
            elsewhere.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).
        input_dim: Number of channels/dimensions in the input.
            Either this argument or the keyword argument `input_shape`must be
            provided when using this layer as the first layer in a model.
        input_length: Length of input sequences, when it is constant.
            This argument is required if you are going to connect
            `Flatten` then `Dense` layers upstream
            (without it, the shape of the dense outputs cannot be computed).

    # Input shape
        3D tensor with shape: `(samples, steps, input_dim)`.

    # Output shape
        3D tensor with shape: `(samples, new_steps, nb_filter)`.
        `steps` value might have changed due to padding.
    """

    def __init__(self, nb_filter, filter_length,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample_length=1, atrous_rate=1,
                 W_regularizer=None, b_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for AtrousConv1D:', border_mode)

        self.atrous_rate = int(atrous_rate)

        super(AtrousConvolution1D, self).__init__(
            nb_filter, filter_length,
            init=init, activation=activation,
            weights=weights, border_mode=border_mode,
            subsample_length=subsample_length,
            W_regularizer=W_regularizer, b_regularizer=b_regularizer,
            activity_regularizer=activity_regularizer,
            W_constraint=W_constraint, b_constraint=b_constraint,
            bias=bias, **kwargs)

    def get_output_shape_for(self, input_shape):
        length = conv_output_length(input_shape[1],
                                    self.filter_length,
                                    self.border_mode,
                                    self.subsample[0],
                                    dilation=self.atrous_rate)
        return (input_shape[0], length, self.nb_filter)

    def call(self, x, mask=None):
        x = K.expand_dims(x, 2)  # add a dummy dimension
        output = K.conv2d(x, self.W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering='tf',
                          filter_dilation=(self.atrous_rate, self.atrous_rate))
        output = K.squeeze(output, 2)  # remove the dummy dimension
        if self.bias:
            output += K.reshape(self.b, (1, 1, self.nb_filter))
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'atrous_rate': self.atrous_rate}
        base_config = super(AtrousConvolution1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Convolution2D(Layer):
    """Convolution operator for filtering windows of two-dimensional inputs.

    When using this layer as the first layer in a model,
    provide the keyword argument `input_shape`
    (tuple of integers, does not include the sample axis),
    e.g. `input_shape=(3, 128, 128)` for 128x128 RGB pictures.

    # Examples

    ```python
        # apply a 3x3 convolution with 64 output filters on a 256x256 image:
        model = Sequential()
        model.add(Convolution2D(64, 3, 3,
                                border_mode='same',
                                input_shape=(3, 256, 256)))
        # now model.output_shape == (None, 64, 256, 256)

        # add a 3x3 convolution on top, with 32 output filters:
        model.add(Convolution2D(32, 3, 3, border_mode='same'))
        # now model.output_shape == (None, 32, 256, 256)
    ```

    # Arguments
        nb_filter: Number of convolution filters to use.
        nb_row: Number of rows in the convolution kernel.
        nb_col: Number of columns in the convolution kernel.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass
            a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample: tuple of length 2. Factor by which to subsample output.
            Also called strides elsewhere.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        dim_ordering: 'th' or 'tf'. In 'th' mode, the channels dimension
            (the depth) is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, nb_filter, new_rows, new_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, new_rows, new_cols, nb_filter)` if dim_ordering='tf'.
        `rows` and `cols` values might have changed due to padding.
    """

    def __init__(self, nb_filter, nb_row, nb_col,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample=(1, 1), dim_ordering='default',
                 W_regularizer=None, b_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution2D:', border_mode)
        self.nb_filter = nb_filter
        self.nb_row = nb_row
        self.nb_col = nb_col
        self.init = initializations.get(init)
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample = tuple(subsample)
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.W_constraint = constraints.get(W_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=4)]
        self.initial_weights = weights
        super(Convolution2D, self).__init__(**kwargs)

    def build(self, input_shape):
        if self.dim_ordering == 'th':
            stack_size = input_shape[1]
            self.W_shape = (self.nb_filter, stack_size, self.nb_row, self.nb_col)
        elif self.dim_ordering == 'tf':
            stack_size = input_shape[3]
            self.W_shape = (self.nb_row, self.nb_col, stack_size, self.nb_filter)
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        self.W = self.add_weight(self.W_shape,
                                 initializer=functools.partial(self.init,
                                                               dim_ordering=self.dim_ordering),
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)
        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            rows = input_shape[2]
            cols = input_shape[3]
        elif self.dim_ordering == 'tf':
            rows = input_shape[1]
            cols = input_shape[2]
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        rows = conv_output_length(rows, self.nb_row,
                                  self.border_mode, self.subsample[0])
        cols = conv_output_length(cols, self.nb_col,
                                  self.border_mode, self.subsample[1])

        if self.dim_ordering == 'th':
            return (input_shape[0], self.nb_filter, rows, cols)
        elif self.dim_ordering == 'tf':
            return (input_shape[0], rows, cols, self.nb_filter)

    def call(self, x, mask=None):
        output = K.conv2d(x, self.W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering=self.dim_ordering,
                          filter_shape=self.W_shape)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, self.nb_filter))
            else:
                raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'nb_row': self.nb_row,
                  'nb_col': self.nb_col,
                  'init': self.init.__name__,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample': self.subsample,
                  'dim_ordering': self.dim_ordering,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'W_constraint': self.W_constraint.get_config() if self.W_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  'bias': self.bias}
        base_config = super(Convolution2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Deconvolution2D(Convolution2D):
    """Transposed convolution operator for filtering windows of 2-D inputs.

    The need for transposed convolutions generally arises from the desire to
    use a transformation going in the opposite direction
    of a normal convolution, i.e., from something that has the shape
    of the output of some convolution to something that has the shape
    of its input while maintaining a connectivity pattern
    that is compatible with said convolution.

    When using this layer as the first layer in a model,
    provide the keyword argument `input_shape`
    (tuple of integers, does not include the sample axis),
    e.g. `input_shape=(3, 128, 128)` for 128x128 RGB pictures.

    To pass the correct `output_shape` to this layer,
    one could use a test model to predict and observe the actual output shape.

    # Examples

    ```python
        # apply a 3x3 transposed convolution
        # with stride 1x1 and 3 output filters on a 12x12 image:
        model = Sequential()
        model.add(Deconvolution2D(3, 3, 3, output_shape=(None, 3, 14, 14),
                                  border_mode='valid',
                                  input_shape=(3, 12, 12)))
        # Note that you will have to change
        # the output_shape depending on the backend used.

        # we can predict with the model and print the shape of the array.
        dummy_input = np.ones((32, 3, 12, 12))
        # For TensorFlow dummy_input = np.ones((32, 12, 12, 3))
        preds = model.predict(dummy_input)
        print(preds.shape)
        # Theano GPU: (None, 3, 13, 13)
        # Theano CPU: (None, 3, 14, 14)
        # TensorFlow: (None, 14, 14, 3)

        # apply a 3x3 transposed convolution
        # with stride 2x2 and 3 output filters on a 12x12 image:
        model = Sequential()
        model.add(Deconvolution2D(3, 3, 3, output_shape=(None, 3, 25, 25),
                                  subsample=(2, 2),
                                  border_mode='valid',
                                  input_shape=(3, 12, 12)))
        model.summary()

        # we can predict with the model and print the shape of the array.
        dummy_input = np.ones((32, 3, 12, 12))
        # For TensorFlow dummy_input = np.ones((32, 12, 12, 3))
        preds = model.predict(dummy_input)
        print(preds.shape)
        # Theano GPU: (None, 3, 25, 25)
        # Theano CPU: (None, 3, 25, 25)
        # TensorFlow: (None, 25, 25, 3)
    ```

    # Arguments
        nb_filter: Number of transposed convolution filters to use.
        nb_row: Number of rows in the transposed convolution kernel.
        nb_col: Number of columns in the transposed convolution kernel.
        output_shape: Output shape of the transposed convolution operation.
            tuple of integers
            `(nb_samples, nb_filter, nb_output_rows, nb_output_cols)`.
             It is better to use
             a dummy input and observe the actual output shape of
             a layer, as specified in the examples.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass
            a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano/TensorFlow function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample: tuple of length 2. Factor by which to oversample output.
            Also called strides elsewhere.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        dim_ordering: 'th' or 'tf'. In 'th' mode, the channels dimension
            (the depth) is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, nb_filter, new_rows, new_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, new_rows, new_cols, nb_filter)` if dim_ordering='tf'.
        `rows` and `cols` values might have changed due to padding.

    # References
        - [A guide to convolution arithmetic for deep learning](https://arxiv.org/abs/1603.07285v1)
        - [Transposed convolution arithmetic](http://deeplearning.net/software/theano_versions/dev/tutorial/conv_arithmetic.html#transposed-convolution-arithmetic)
        - [Deconvolutional Networks](http://www.matthewzeiler.com/pubs/cvpr2010/cvpr2010.pdf)
    """

    def __init__(self, nb_filter, nb_row, nb_col, output_shape,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample=(1, 1),
                 dim_ordering='default',
                 W_regularizer=None, b_regularizer=None, activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Deconvolution2D:', border_mode)

        self.output_shape_ = output_shape

        super(Deconvolution2D, self).__init__(nb_filter, nb_row, nb_col,
                                              init=init,
                                              activation=activation,
                                              weights=weights,
                                              border_mode=border_mode,
                                              subsample=subsample,
                                              dim_ordering=dim_ordering,
                                              W_regularizer=W_regularizer,
                                              b_regularizer=b_regularizer,
                                              activity_regularizer=activity_regularizer,
                                              W_constraint=W_constraint,
                                              b_constraint=b_constraint,
                                              bias=bias,
                                              **kwargs)

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            rows = self.output_shape_[2]
            cols = self.output_shape_[3]
        elif self.dim_ordering == 'tf':
            rows = self.output_shape_[1]
            cols = self.output_shape_[2]
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        if self.dim_ordering == 'th':
            return (input_shape[0], self.nb_filter, rows, cols)
        elif self.dim_ordering == 'tf':
            return (input_shape[0], rows, cols, self.nb_filter)

    def call(self, x, mask=None):
        output = K.deconv2d(x, self.W, self.output_shape_,
                            strides=self.subsample,
                            border_mode=self.border_mode,
                            dim_ordering=self.dim_ordering,
                            filter_shape=self.W_shape)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, self.nb_filter))
            else:
                raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'output_shape': self.output_shape_}
        base_config = super(Deconvolution2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class AtrousConvolution2D(Convolution2D):
    """Atrous Convolution operator for filtering windows of 2-D inputs.

    A.k.a dilated convolution or convolution with holes.
    When using this layer as the first layer in a model,
    provide the keyword argument `input_shape`
    (tuple of integers, does not include the sample axis),
    e.g. `input_shape=(3, 128, 128)` for 128x128 RGB pictures.

    # Examples

    ```python
        # apply a 3x3 convolution with atrous rate 2x2
        # and 64 output filters on a 256x256 image:
        model = Sequential()
        model.add(AtrousConvolution2D(64, 3, 3, atrous_rate=(2,2),
                                      border_mode='valid',
                                      input_shape=(3, 256, 256)))
        # now the actual kernel size is dilated
        # from 3x3 to 5x5 (3+(3-1)*(2-1)=5)
        # thus model.output_shape == (None, 64, 252, 252)
    ```

    # Arguments
        nb_filter: Number of convolution filters to use.
        nb_row: Number of rows in the convolution kernel.
        nb_col: Number of columns in the convolution kernel.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass
            a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample: tuple of length 2. Factor by which to subsample output.
            Also called strides elsewhere.
        atrous_rate: tuple of length 2. Factor for kernel dilation.
            Also called filter_dilation elsewhere.
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        dim_ordering: 'th' or 'tf'. In 'th' mode, the channels dimension
            (the depth) is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, nb_filter, new_rows, new_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, new_rows, new_cols, nb_filter)` if dim_ordering='tf'.
        `rows` and `cols` values might have changed due to padding.

    # References
        - [Multi-Scale Context Aggregation by Dilated Convolutions](https://arxiv.org/abs/1511.07122)
    """

    def __init__(self, nb_filter, nb_row, nb_col,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample=(1, 1),
                 atrous_rate=(1, 1), dim_ordering='default',
                 W_regularizer=None, b_regularizer=None,
                 activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for AtrousConv2D:', border_mode)

        self.atrous_rate = tuple(atrous_rate)

        super(AtrousConvolution2D, self).__init__(nb_filter, nb_row, nb_col,
                                                  init=init,
                                                  activation=activation,
                                                  weights=weights,
                                                  border_mode=border_mode,
                                                  subsample=subsample,
                                                  dim_ordering=dim_ordering,
                                                  W_regularizer=W_regularizer,
                                                  b_regularizer=b_regularizer,
                                                  activity_regularizer=activity_regularizer,
                                                  W_constraint=W_constraint,
                                                  b_constraint=b_constraint,
                                                  bias=bias,
                                                  **kwargs)

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            rows = input_shape[2]
            cols = input_shape[3]
        elif self.dim_ordering == 'tf':
            rows = input_shape[1]
            cols = input_shape[2]
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        rows = conv_output_length(rows, self.nb_row, self.border_mode,
                                  self.subsample[0],
                                  dilation=self.atrous_rate[0])
        cols = conv_output_length(cols, self.nb_col, self.border_mode,
                                  self.subsample[1],
                                  dilation=self.atrous_rate[1])

        if self.dim_ordering == 'th':
            return (input_shape[0], self.nb_filter, rows, cols)
        elif self.dim_ordering == 'tf':
            return (input_shape[0], rows, cols, self.nb_filter)

    def call(self, x, mask=None):
        output = K.conv2d(x, self.W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering=self.dim_ordering,
                          filter_shape=self.W_shape,
                          filter_dilation=self.atrous_rate)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, self.nb_filter))
            else:
                raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'atrous_rate': self.atrous_rate}
        base_config = super(AtrousConvolution2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class SeparableConvolution2D(Layer):
    """Separable convolution operator for 2D inputs.

    Separable convolutions consist in first performing
    a depthwise spatial convolution
    (which acts on each input channel separately)
    followed by a pointwise convolution which mixes together the resulting
    output channels. The `depth_multiplier` argument controls how many
    output channels are generated per input channel in the depthwise step.

    Intuitively, separable convolutions can be understood as
    a way to factorize a convolution kernel into two smaller kernels,
    or as an extreme version of an Inception block.

    When using this layer as the first layer in a model,
    provide the keyword argument `input_shape`
    (tuple of integers, does not include the sample axis),
    e.g. `input_shape=(3, 128, 128)` for 128x128 RGB pictures.

    # Theano warning

    This layer is only available with the
    TensorFlow backend for the time being.

    # Arguments
        nb_filter: Number of convolution filters to use.
        nb_row: Number of rows in the convolution kernel.
        nb_col: Number of columns in the convolution kernel.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass
            a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of numpy arrays to set as initial weights.
        border_mode: 'valid' or 'same'.
        subsample: tuple of length 2. Factor by which to subsample output.
            Also called strides elsewhere.
        depth_multiplier: how many output channel to use per input channel
            for the depthwise convolution step.
        depthwise_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the depthwise weights matrix.
        pointwise_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the pointwise weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        depthwise_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the depthwise weights matrix.
        pointwise_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the pointwise weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        dim_ordering: 'th' or 'tf'. In 'th' mode, the channels dimension
            (the depth) is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, nb_filter, new_rows, new_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, new_rows, new_cols, nb_filter)` if dim_ordering='tf'.
        `rows` and `cols` values might have changed due to padding.
    """

    def __init__(self, nb_filter, nb_row, nb_col,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample=(1, 1),
                 depth_multiplier=1, dim_ordering='default',
                 depthwise_regularizer=None, pointwise_regularizer=None,
                 b_regularizer=None, activity_regularizer=None,
                 depthwise_constraint=None, pointwise_constraint=None,
                 b_constraint=None,
                 bias=True, **kwargs):

        if K.backend() != 'tensorflow':
            raise RuntimeError('SeparableConv2D is only available '
                               'with TensorFlow for the time being.')

        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()

        if border_mode not in {'valid', 'same'}:
            raise ValueError('Invalid border mode for SeparableConv2D:', border_mode)

        if border_mode not in {'valid', 'same'}:
            raise ValueError('Invalid border mode for SeparableConv2D:', border_mode)
        self.nb_filter = nb_filter
        self.nb_row = nb_row
        self.nb_col = nb_col
        self.init = initializations.get(init)
        self.activation = activations.get(activation)
        if border_mode not in {'valid', 'same'}:
            raise ValueError('border_mode must be in {valid, same}.')
        self.border_mode = border_mode
        self.subsample = tuple(subsample)
        self.depth_multiplier = depth_multiplier
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering

        self.depthwise_regularizer = regularizers.get(depthwise_regularizer)
        self.pointwise_regularizer = regularizers.get(pointwise_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.depthwise_constraint = constraints.get(depthwise_constraint)
        self.pointwise_constraint = constraints.get(pointwise_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=4)]
        self.initial_weights = weights
        super(SeparableConvolution2D, self).__init__(**kwargs)

    def build(self, input_shape):
        if self.dim_ordering == 'th':
            stack_size = input_shape[1]
            depthwise_shape = (self.depth_multiplier, stack_size, self.nb_row, self.nb_col)
            pointwise_shape = (self.nb_filter, self.depth_multiplier * stack_size, 1, 1)
        elif self.dim_ordering == 'tf':
            stack_size = input_shape[3]
            depthwise_shape = (self.nb_row, self.nb_col, stack_size, self.depth_multiplier)
            pointwise_shape = (1, 1, self.depth_multiplier * stack_size, self.nb_filter)
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        self.depthwise_kernel = self.add_weight(depthwise_shape,
                                                initializer=functools.partial(self.init,
                                                                              dim_ordering=self.dim_ordering),
                                                regularizer=self.depthwise_regularizer,
                                                constraint=self.depthwise_constraint,
                                                name='{}_depthwise_kernel'.format(self.name))
        self.pointwise_kernel = self.add_weight(pointwise_shape,
                                                initializer=functools.partial(self.init,
                                                                              dim_ordering=self.dim_ordering),
                                                regularizer=self.pointwise_regularizer,
                                                constraint=self.pointwise_constraint,
                                                name='{}_pointwise_kernel'.format(self.name))
        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            rows = input_shape[2]
            cols = input_shape[3]
        elif self.dim_ordering == 'tf':
            rows = input_shape[1]
            cols = input_shape[2]
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        rows = conv_output_length(rows, self.nb_row,
                                  self.border_mode, self.subsample[0])
        cols = conv_output_length(cols, self.nb_col,
                                  self.border_mode, self.subsample[1])

        if self.dim_ordering == 'th':
            return (input_shape[0], self.nb_filter, rows, cols)
        elif self.dim_ordering == 'tf':
            return (input_shape[0], rows, cols, self.nb_filter)
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        output = K.separable_conv2d(x, self.depthwise_kernel,
                                    self.pointwise_kernel,
                                    strides=self.subsample,
                                    border_mode=self.border_mode,
                                    dim_ordering=self.dim_ordering)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, self.nb_filter))
            else:
                raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'nb_row': self.nb_row,
                  'nb_col': self.nb_col,
                  'init': self.init.__name__,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample': self.subsample,
                  'depth_multiplier': self.depth_multiplier,
                  'dim_ordering': self.dim_ordering,
                  'depthwise_regularizer': self.depthwise_regularizer.get_config() if self.depthwise_regularizer else None,
                  'pointwise_regularizer': self.depthwise_regularizer.get_config() if self.depthwise_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'depthwise_constraint': self.depthwise_constraint.get_config() if self.depthwise_constraint else None,
                  'pointwise_constraint': self.pointwise_constraint.get_config() if self.pointwise_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  'bias': self.bias}
        base_config = super(SeparableConvolution2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Convolution3D(Layer):
    """Convolution operator for filtering windows of three-dimensional inputs.

    When using this layer as the first layer in a model,
    provide the keyword argument `input_shape`
    (tuple of integers, does not include the sample axis),
    e.g. `input_shape=(3, 10, 128, 128)` for 10 frames of 128x128 RGB pictures.

    # Arguments
        nb_filter: Number of convolution filters to use.
        kernel_dim1: Length of the first dimension in the convolution kernel.
        kernel_dim2: Length of the second dimension in the convolution kernel.
        kernel_dim3: Length of the third dimension in the convolution kernel.
        init: name of initialization function for the weights of the layer
            (see [initializations](../initializations.md)), or alternatively,
            Theano function to use for weights initialization.
            This parameter is only relevant if you don't pass
            a `weights` argument.
        activation: name of activation function to use
            (see [activations](../activations.md)),
            or alternatively, elementwise Theano function.
            If you don't specify anything, no activation is applied
            (ie. "linear" activation: a(x) = x).
        weights: list of Numpy arrays to set as initial weights.
        border_mode: 'valid', 'same' or 'full'
            ('full' requires the Theano backend).
        subsample: tuple of length 3. Factor by which to subsample output.
            Also called strides elsewhere.
            Note: 'subsample' is implemented by slicing
            the output of conv3d with strides=(1,1,1).
        W_regularizer: instance of [WeightRegularizer](../regularizers.md)
            (eg. L1 or L2 regularization), applied to the main weights matrix.
        b_regularizer: instance of [WeightRegularizer](../regularizers.md),
            applied to the bias.
        activity_regularizer: instance of [ActivityRegularizer](../regularizers.md),
            applied to the network output.
        W_constraint: instance of the [constraints](../constraints.md) module
            (eg. maxnorm, nonneg), applied to the main weights matrix.
        b_constraint: instance of the [constraints](../constraints.md) module,
            applied to the bias.
        dim_ordering: 'th' or 'tf'. In 'th' mode, the channels dimension
            (the depth) is at index 1, in 'tf' mode is it at index 4.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".
        bias: whether to include a bias
            (i.e. make the layer affine rather than linear).

    # Input shape
        5D tensor with shape:
        `(samples, channels, conv_dim1, conv_dim2, conv_dim3)` if dim_ordering='th'
        or 5D tensor with shape:
        `(samples, conv_dim1, conv_dim2, conv_dim3, channels)` if dim_ordering='tf'.

    # Output shape
        5D tensor with shape:
        `(samples, nb_filter, new_conv_dim1, new_conv_dim2, new_conv_dim3)` if dim_ordering='th'
        or 5D tensor with shape:
        `(samples, new_conv_dim1, new_conv_dim2, new_conv_dim3, nb_filter)` if dim_ordering='tf'.
        `new_conv_dim1`, `new_conv_dim2` and `new_conv_dim3` values might have changed due to padding.
    """

    def __init__(self, nb_filter, kernel_dim1, kernel_dim2, kernel_dim3,
                 init='glorot_uniform', activation=None, weights=None,
                 border_mode='valid', subsample=(1, 1, 1), dim_ordering='default',
                 W_regularizer=None, b_regularizer=None, activity_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()

        if border_mode not in {'valid', 'same', 'full'}:
            raise ValueError('Invalid border mode for Convolution3D:', border_mode)
        self.nb_filter = nb_filter
        self.kernel_dim1 = kernel_dim1
        self.kernel_dim2 = kernel_dim2
        self.kernel_dim3 = kernel_dim3
        self.init = initializations.get(init)
        self.activation = activations.get(activation)
        self.border_mode = border_mode
        self.subsample = tuple(subsample)
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.activity_regularizer = regularizers.get(activity_regularizer)

        self.W_constraint = constraints.get(W_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.input_spec = [InputSpec(ndim=5)]
        self.initial_weights = weights
        super(Convolution3D, self).__init__(**kwargs)

    def build(self, input_shape):
        assert len(input_shape) == 5

        if self.dim_ordering == 'th':
            stack_size = input_shape[1]
            self.W_shape = (self.nb_filter, stack_size,
                            self.kernel_dim1, self.kernel_dim2, self.kernel_dim3)
        elif self.dim_ordering == 'tf':
            stack_size = input_shape[4]
            self.W_shape = (self.kernel_dim1, self.kernel_dim2, self.kernel_dim3,
                            stack_size, self.nb_filter)
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        self.W = self.add_weight(self.W_shape,
                                 initializer=functools.partial(self.init,
                                                               dim_ordering=self.dim_ordering),
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)
        if self.bias:
            self.b = self.add_weight((self.nb_filter,),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        if self.initial_weights is not None:
            self.set_weights(self.initial_weights)
            del self.initial_weights
        self.built = True

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            conv_dim1 = input_shape[2]
            conv_dim2 = input_shape[3]
            conv_dim3 = input_shape[4]
        elif self.dim_ordering == 'tf':
            conv_dim1 = input_shape[1]
            conv_dim2 = input_shape[2]
            conv_dim3 = input_shape[3]
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

        conv_dim1 = conv_output_length(conv_dim1, self.kernel_dim1,
                                       self.border_mode, self.subsample[0])
        conv_dim2 = conv_output_length(conv_dim2, self.kernel_dim2,
                                       self.border_mode, self.subsample[1])
        conv_dim3 = conv_output_length(conv_dim3, self.kernel_dim3,
                                       self.border_mode, self.subsample[2])

        if self.dim_ordering == 'th':
            return (input_shape[0], self.nb_filter, conv_dim1, conv_dim2, conv_dim3)
        elif self.dim_ordering == 'tf':
            return (input_shape[0], conv_dim1, conv_dim2, conv_dim3, self.nb_filter)
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        output = K.conv3d(x, self.W, strides=self.subsample,
                          border_mode=self.border_mode,
                          dim_ordering=self.dim_ordering,
                          filter_shape=self.W_shape)
        if self.bias:
            if self.dim_ordering == 'th':
                output += K.reshape(self.b, (1, self.nb_filter, 1, 1, 1))
            elif self.dim_ordering == 'tf':
                output += K.reshape(self.b, (1, 1, 1, 1, self.nb_filter))
            else:
                raise ValueError('Invalid dim_ordering:', self.dim_ordering)
        output = self.activation(output)
        return output

    def get_config(self):
        config = {'nb_filter': self.nb_filter,
                  'kernel_dim1': self.kernel_dim1,
                  'kernel_dim2': self.kernel_dim2,
                  'kernel_dim3': self.kernel_dim3,
                  'dim_ordering': self.dim_ordering,
                  'init': self.init.__name__,
                  'activation': self.activation.__name__,
                  'border_mode': self.border_mode,
                  'subsample': self.subsample,
                  'W_regularizer': self.W_regularizer.get_config() if self.W_regularizer else None,
                  'b_regularizer': self.b_regularizer.get_config() if self.b_regularizer else None,
                  'activity_regularizer': self.activity_regularizer.get_config() if self.activity_regularizer else None,
                  'W_constraint': self.W_constraint.get_config() if self.W_constraint else None,
                  'b_constraint': self.b_constraint.get_config() if self.b_constraint else None,
                  'bias': self.bias}
        base_config = super(Convolution3D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class UpSampling1D(Layer):
    """Upsampling layer for 1D inputs.

    Repeats each temporal step `length` times along the time axis.

    # Arguments
        length: integer. Upsampling factor.

    # Input shape
        3D tensor with shape: `(samples, steps, features)`.

    # Output shape
        3D tensor with shape: `(samples, upsampled_steps, features)`.
    """

    def __init__(self, length=2, **kwargs):
        self.length = length
        self.input_spec = [InputSpec(ndim=3)]
        super(UpSampling1D, self).__init__(**kwargs)

    def get_output_shape_for(self, input_shape):
        length = self.length * input_shape[1] if input_shape[1] is not None else None
        return (input_shape[0], length, input_shape[2])

    def call(self, x, mask=None):
        output = K.repeat_elements(x, self.length, axis=1)
        return output

    def get_config(self):
        config = {'length': self.length}
        base_config = super(UpSampling1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class UpSampling2D(Layer):
    """Upsampling layer for 2D inputs.

    Repeats the rows and columns of the data
    by size[0] and size[1] respectively.

    # Arguments
        size: tuple of 2 integers. The upsampling factors for rows and columns.
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, channels, upsampled_rows, upsampled_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, upsampled_rows, upsampled_cols, channels)` if dim_ordering='tf'.
    """

    def __init__(self, size=(2, 2), dim_ordering='default', **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        self.size = tuple(size)
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=4)]
        super(UpSampling2D, self).__init__(**kwargs)

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            width = self.size[0] * input_shape[2] if input_shape[2] is not None else None
            height = self.size[1] * input_shape[3] if input_shape[3] is not None else None
            return (input_shape[0],
                    input_shape[1],
                    width,
                    height)
        elif self.dim_ordering == 'tf':
            width = self.size[0] * input_shape[1] if input_shape[1] is not None else None
            height = self.size[1] * input_shape[2] if input_shape[2] is not None else None
            return (input_shape[0],
                    width,
                    height,
                    input_shape[3])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        return K.resize_images(x, self.size[0], self.size[1],
                               self.dim_ordering)

    def get_config(self):
        config = {'size': self.size}
        base_config = super(UpSampling2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class UpSampling3D(Layer):
    """Upsampling layer for 3D inputs.

    Repeats the 1st, 2nd and 3rd dimensions
    of the data by size[0], size[1] and size[2] respectively.

    # Arguments
        size: tuple of 3 integers. The upsampling factors for dim1, dim2 and dim3.
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 4.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        5D tensor with shape:
        `(samples, channels, dim1, dim2, dim3)` if dim_ordering='th'
        or 5D tensor with shape:
        `(samples, dim1, dim2, dim3, channels)` if dim_ordering='tf'.

    # Output shape
        5D tensor with shape:
        `(samples, channels, upsampled_dim1, upsampled_dim2, upsampled_dim3)` if dim_ordering='th'
        or 5D tensor with shape:
        `(samples, upsampled_dim1, upsampled_dim2, upsampled_dim3, channels)` if dim_ordering='tf'.
    """

    def __init__(self, size=(2, 2, 2), dim_ordering='default', **kwargs):
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        self.size = tuple(size)
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=5)]
        super(UpSampling3D, self).__init__(**kwargs)

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            dim1 = self.size[0] * input_shape[2] if input_shape[2] is not None else None
            dim2 = self.size[1] * input_shape[3] if input_shape[3] is not None else None
            dim3 = self.size[2] * input_shape[4] if input_shape[4] is not None else None
            return (input_shape[0],
                    input_shape[1],
                    dim1,
                    dim2,
                    dim3)
        elif self.dim_ordering == 'tf':
            dim1 = self.size[0] * input_shape[1] if input_shape[1] is not None else None
            dim2 = self.size[1] * input_shape[2] if input_shape[2] is not None else None
            dim3 = self.size[2] * input_shape[3] if input_shape[3] is not None else None
            return (input_shape[0],
                    dim1,
                    dim2,
                    dim3,
                    input_shape[4])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        return K.resize_volumes(x, self.size[0], self.size[1], self.size[2],
                                self.dim_ordering)

    def get_config(self):
        config = {'size': self.size}
        base_config = super(UpSampling3D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class ZeroPadding1D(Layer):
    """Zero-padding layer for 1D input (e.g. temporal sequence).

    # Arguments
        padding: int, or tuple of int (length 2), or dictionary.
            - If int:
            How many zeros to add at the beginning and end of
            the padding dimension (axis 1).
            - If tuple of int (length 2)
            How many zeros to add at the beginning and at the end of
            the padding dimension, in order '(left_pad, right_pad)'.
            - If dictionary: should contain the keys
            {'left_pad', 'right_pad'}.
            If any key is missing, default value of 0 will be used for the missing key.

    # Input shape
        3D tensor with shape `(samples, axis_to_pad, features)`

    # Output shape
        3D tensor with shape `(samples, padded_axis, features)`
    """

    def __init__(self, padding=1, **kwargs):
        super(ZeroPadding1D, self).__init__(**kwargs)
        self.padding = padding

        if isinstance(padding, int):
            self.left_pad = padding
            self.right_pad = padding

        elif isinstance(padding, dict):
            if set(padding.keys()) <= {'left_pad', 'right_pad'}:
                self.left_pad = padding.get('left_pad', 0)
                self.right_pad = padding.get('right_pad', 0)
            else:
                raise ValueError('Unexpected key found in `padding` dictionary. '
                                 'Keys have to be in {"left_pad", "right_pad"}. '
                                 'Found: ' + str(padding.keys()))
        else:
            padding = tuple(padding)
            if len(padding) != 2:
                raise ValueError('`padding` should be int, or dict with keys '
                                 '{"left_pad", "right_pad"}, or tuple of length 2. '
                                 'Found: ' + str(padding))
            self.left_pad = padding[0]
            self.right_pad = padding[1]
        self.input_spec = [InputSpec(ndim=3)]

    def get_output_shape_for(self, input_shape):
        length = input_shape[1] + self.left_pad + self.right_pad if input_shape[1] is not None else None
        return (input_shape[0],
                length,
                input_shape[2])

    def call(self, x, mask=None):
        return K.asymmetric_temporal_padding(x, left_pad=self.left_pad, right_pad=self.right_pad)

    def get_config(self):
        config = {'padding': self.padding}
        base_config = super(ZeroPadding1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class ZeroPadding2D(Layer):
    """Zero-padding layer for 2D input (e.g. picture).

    # Arguments
        padding: tuple of int (length 2), or tuple of int (length 4), or dictionary.
            - If tuple of int (length 2):
            How many zeros to add at the beginning and end of
            the 2 padding dimensions (rows and cols).
            - If tuple of int (length 4):
            How many zeros to add at the beginning and at the end of
            the 2 padding dimensions (rows and cols), in the order
            '(top_pad, bottom_pad, left_pad, right_pad)'.
            - If dictionary: should contain the keys
            {'top_pad', 'bottom_pad', 'left_pad', 'right_pad'}.
            If any key is missing, default value of 0 will be used for the missing key.
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        4D tensor with shape:
        `(samples, channels, rows, cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, rows, cols, channels)` if dim_ordering='tf'.

    # Output shape
        4D tensor with shape:
        `(samples, channels, padded_rows, padded_cols)` if dim_ordering='th'
        or 4D tensor with shape:
        `(samples, padded_rows, padded_cols, channels)` if dim_ordering='tf'.
    """

    def __init__(self,
                 padding=(1, 1),
                 dim_ordering='default',
                 **kwargs):
        super(ZeroPadding2D, self).__init__(**kwargs)
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()

        self.padding = padding
        if isinstance(padding, dict):
            if set(padding.keys()) <= {'top_pad', 'bottom_pad', 'left_pad', 'right_pad'}:
                self.top_pad = padding.get('top_pad', 0)
                self.bottom_pad = padding.get('bottom_pad', 0)
                self.left_pad = padding.get('left_pad', 0)
                self.right_pad = padding.get('right_pad', 0)
            else:
                raise ValueError('Unexpected key found in `padding` dictionary. '
                                 'Keys have to be in {"top_pad", "bottom_pad", '
                                 '"left_pad", "right_pad"}.'
                                 'Found: ' + str(padding.keys()))
        else:
            padding = tuple(padding)
            if len(padding) == 2:
                self.top_pad = padding[0]
                self.bottom_pad = padding[0]
                self.left_pad = padding[1]
                self.right_pad = padding[1]
            elif len(padding) == 4:
                self.top_pad = padding[0]
                self.bottom_pad = padding[1]
                self.left_pad = padding[2]
                self.right_pad = padding[3]
            else:
                raise TypeError('`padding` should be tuple of int '
                                'of length 2 or 4, or dict. '
                                'Found: ' + str(padding))

        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=4)]

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            rows = input_shape[2] + self.top_pad + self.bottom_pad if input_shape[2] is not None else None
            cols = input_shape[3] + self.left_pad + self.right_pad if input_shape[3] is not None else None
            return (input_shape[0],
                    input_shape[1],
                    rows,
                    cols)
        elif self.dim_ordering == 'tf':
            rows = input_shape[1] + self.top_pad + self.bottom_pad if input_shape[1] is not None else None
            cols = input_shape[2] + self.left_pad + self.right_pad if input_shape[2] is not None else None
            return (input_shape[0],
                    rows,
                    cols,
                    input_shape[3])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        return K.asymmetric_spatial_2d_padding(x,
                                               top_pad=self.top_pad,
                                               bottom_pad=self.bottom_pad,
                                               left_pad=self.left_pad,
                                               right_pad=self.right_pad,
                                               dim_ordering=self.dim_ordering)

    def get_config(self):
        config = {'padding': self.padding}
        base_config = super(ZeroPadding2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class ZeroPadding3D(Layer):
    """Zero-padding layer for 3D data (spatial or spatio-temporal).

    # Arguments
        padding: tuple of int (length 3)
            How many zeros to add at the beginning and end of
            the 3 padding dimensions (axis 3, 4 and 5).
            Currently only symmetric padding is supported.
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 4.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        5D tensor with shape:
        `(samples, depth, first_axis_to_pad, second_axis_to_pad, third_axis_to_pad)`

    # Output shape
        5D tensor with shape:
        `(samples, depth, first_padded_axis, second_padded_axis, third_axis_to_pad)`
    """

    def __init__(self, padding=(1, 1, 1), dim_ordering='default', **kwargs):
        super(ZeroPadding3D, self).__init__(**kwargs)
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        self.padding = tuple(padding)
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=5)]

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            dim1 = input_shape[2] + 2 * self.padding[0] if input_shape[2] is not None else None
            dim2 = input_shape[3] + 2 * self.padding[1] if input_shape[3] is not None else None
            dim3 = input_shape[4] + 2 * self.padding[2] if input_shape[4] is not None else None
            return (input_shape[0],
                    input_shape[1],
                    dim1,
                    dim2,
                    dim3)
        elif self.dim_ordering == 'tf':
            dim1 = input_shape[1] + 2 * self.padding[0] if input_shape[1] is not None else None
            dim2 = input_shape[2] + 2 * self.padding[1] if input_shape[2] is not None else None
            dim3 = input_shape[3] + 2 * self.padding[2] if input_shape[3] is not None else None
            return (input_shape[0],
                    dim1,
                    dim2,
                    dim3,
                    input_shape[4])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        return K.spatial_3d_padding(x, padding=self.padding,
                                    dim_ordering=self.dim_ordering)

    def get_config(self):
        config = {'padding': self.padding}
        base_config = super(ZeroPadding3D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Cropping1D(Layer):
    """Cropping layer for 1D input (e.g. temporal sequence).

    It crops along the time dimension (axis 1).

    # Arguments
        cropping: tuple of int (length 2)
            How many units should be trimmed off at the beginning and end of
            the cropping dimension (axis 1).

    # Input shape
        3D tensor with shape `(samples, axis_to_crop, features)`

    # Output shape
        3D tensor with shape `(samples, cropped_axis, features)`
    """

    def __init__(self, cropping=(1, 1), **kwargs):
        super(Cropping1D, self).__init__(**kwargs)
        self.cropping = tuple(cropping)
        if len(self.cropping) != 2:
            raise ValueError('`cropping` must be a tuple length of 2.')
        self.input_spec = [InputSpec(ndim=3)]

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        self.built = True

    def get_output_shape_for(self, input_shape):
        if input_shape[1] is not None:
            length = input_shape[1] - self.cropping[0] - self.cropping[1]
        else:
            length = None
        return (input_shape[0],
                length,
                input_shape[2])

    def call(self, x, mask=None):
        if self.cropping[1] == 0:
            return x[:, self.cropping[0]:, :]
        else:
            return x[:, self.cropping[0]:-self.cropping[1], :]

    def get_config(self):
        config = {'cropping': self.cropping}
        base_config = super(Cropping1D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Cropping2D(Layer):
    """Cropping layer for 2D input (e.g. picture).

    It crops along spatial dimensions, i.e. width and height.

    # Arguments
        cropping: tuple of tuple of int (length 2)
            How many units should be trimmed off at the beginning and end of
            the 2 cropping dimensions (width, height).
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 3.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        4D tensor with shape:
        `(samples, depth, first_axis_to_crop, second_axis_to_crop)`

    # Output shape
        4D tensor with shape:
        `(samples, depth, first_cropped_axis, second_cropped_axis)`

    # Examples

    ```python
        # Crop the input 2D images or feature maps
        model = Sequential()
        model.add(Cropping2D(cropping=((2, 2), (4, 4)), input_shape=(3, 28, 28)))
        # now model.output_shape == (None, 3, 24, 20)
        model.add(Convolution2D(64, 3, 3, border_mode='same))
        model.add(Cropping2D(cropping=((2, 2), (2, 2))))
        # now model.output_shape == (None, 64, 20, 16)

    ```
    """

    def __init__(self, cropping=((0, 0), (0, 0)), dim_ordering='default', **kwargs):
        super(Cropping2D, self).__init__(**kwargs)
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        self.cropping = tuple(cropping)
        if len(self.cropping) != 2:
            raise ValueError('`cropping` must be a tuple length of 2.')
        if len(self.cropping[0]) != 2:
            raise ValueError('`cropping[0]` must be a tuple length of 2.')
        if len(self.cropping[1]) != 2:
            raise ValueError('`cropping[1]` must be a tuple length of 2.')
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=4)]

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        self.built = True

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            return (input_shape[0],
                    input_shape[1],
                    input_shape[2] - self.cropping[0][0] - self.cropping[0][1],
                    input_shape[3] - self.cropping[1][0] - self.cropping[1][1])
        elif self.dim_ordering == 'tf':
            return (input_shape[0],
                    input_shape[1] - self.cropping[0][0] - self.cropping[0][1],
                    input_shape[2] - self.cropping[1][0] - self.cropping[1][1],
                    input_shape[3])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        if self.dim_ordering == 'th':
            if self.cropping[0][1] == self.cropping[1][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:]
            elif self.cropping[0][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1]]
            elif self.cropping[1][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:]
            return x[:,
                     :,
                     self.cropping[0][0]:-self.cropping[0][1],
                     self.cropping[1][0]:-self.cropping[1][1]]
        elif self.dim_ordering == 'tf':
            if self.cropping[0][1] == self.cropping[1][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:,
                         :]
            elif self.cropping[0][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1],
                         :]
            elif self.cropping[1][1] == 0:
                return x[:,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:,
                         :]
            return x[:,
                     self.cropping[0][0]:-self.cropping[0][1],
                     self.cropping[1][0]:-self.cropping[1][1],
                     :]

    def get_config(self):
        config = {'cropping': self.cropping}
        base_config = super(Cropping2D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


class Cropping3D(Layer):
    """Cropping layer for 3D data (e.g. spatial or spatio-temporal).

    # Arguments
        cropping: tuple of tuple of int (length 3)
            How many units should be trimmed off at the beginning and end of
            the 3 cropping dimensions (kernel_dim1, kernel_dim2, kernerl_dim3).
        dim_ordering: 'th' or 'tf'.
            In 'th' mode, the channels dimension (the depth)
            is at index 1, in 'tf' mode is it at index 4.
            It defaults to the `image_dim_ordering` value found in your
            Keras config file at `~/.keras/keras.json`.
            If you never set it, then it will be "tf".

    # Input shape
        5D tensor with shape:
        `(samples, depth, first_axis_to_crop, second_axis_to_crop, third_axis_to_crop)`

    # Output shape
        5D tensor with shape:
        `(samples, depth, first_cropped_axis, second_cropped_axis, third_cropped_axis)`

    """

    def __init__(self, cropping=((1, 1), (1, 1), (1, 1)),
                 dim_ordering='default', **kwargs):
        super(Cropping3D, self).__init__(**kwargs)
        if dim_ordering == 'default':
            dim_ordering = K.image_dim_ordering()
        self.cropping = tuple(cropping)
        if len(self.cropping) != 3:
            raise ValueError('`cropping` must be a tuple length of 3.')
        if len(self.cropping[0]) != 2:
            raise ValueError('`cropping[0]` must be a tuple length of 2.')
        if len(self.cropping[1]) != 2:
            raise ValueError('`cropping[1]` must be a tuple length of 2.')
        if len(self.cropping[2]) != 2:
            raise ValueError('`cropping[2]` must be a tuple length of 2.')
        if dim_ordering not in {'tf', 'th'}:
            raise ValueError('dim_ordering must be in {tf, th}.')
        self.dim_ordering = dim_ordering
        self.input_spec = [InputSpec(ndim=5)]

    def build(self, input_shape):
        self.input_spec = [InputSpec(shape=input_shape)]
        self.built = True

    def get_output_shape_for(self, input_shape):
        if self.dim_ordering == 'th':
            dim1 = input_shape[2] - self.cropping[0][0] - self.cropping[0][1] if input_shape[2] is not None else None
            dim2 = input_shape[3] - self.cropping[1][0] - self.cropping[1][1] if input_shape[3] is not None else None
            dim3 = input_shape[4] - self.cropping[2][0] - self.cropping[2][1] if input_shape[4] is not None else None
            return (input_shape[0],
                    input_shape[1],
                    dim1,
                    dim2,
                    dim3)
        elif self.dim_ordering == 'tf':
            dim1 = input_shape[1] - self.cropping[0][0] - self.cropping[0][1] if input_shape[1] is not None else None
            dim2 = input_shape[2] - self.cropping[1][0] - self.cropping[1][1] if input_shape[2] is not None else None
            dim3 = input_shape[3] - self.cropping[2][0] - self.cropping[2][1] if input_shape[3] is not None else None
            return (input_shape[0],
                    dim1,
                    dim2,
                    dim3,
                    input_shape[4])
        else:
            raise ValueError('Invalid dim_ordering:', self.dim_ordering)

    def call(self, x, mask=None):
        if self.dim_ordering == 'th':
            if self.cropping[0][1] == self.cropping[1][1] == self.cropping[2][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:,
                         self.cropping[2][0]:]
            elif self.cropping[0][1] == self.cropping[1][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:,
                         self.cropping[2][0]:-self.cropping[2][1]]
            elif self.cropping[1][1] == self.cropping[2][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:,
                         self.cropping[2][0]:]
            elif self.cropping[0][1] == self.cropping[2][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:]
            elif self.cropping[0][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:-self.cropping[2][1]]
            elif self.cropping[1][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:,
                         self.cropping[2][0]:-self.cropping[2][1]]
            elif self.cropping[2][1] == 0:
                return x[:,
                         :,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:]
            return x[:,
                     :,
                     self.cropping[0][0]:-self.cropping[0][1],
                     self.cropping[1][0]:-self.cropping[1][1],
                     self.cropping[2][0]:-self.cropping[2][1]]
        elif self.dim_ordering == 'tf':
            if self.cropping[0][1] == self.cropping[1][1] == self.cropping[2][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:,
                         self.cropping[2][0]:,
                         :]
            elif self.cropping[0][1] == self.cropping[1][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:,
                         self.cropping[2][0]:-self.cropping[2][1],
                         :]
            elif self.cropping[1][1] == self.cropping[2][1] == 0:
                return x[:,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:,
                         self.cropping[2][0]:,
                         :]
            elif self.cropping[0][1] == self.cropping[2][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:,
                         :]
            elif self.cropping[0][1] == 0:
                return x[:,
                         self.cropping[0][0]:,
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:-self.cropping[2][1],
                         :]
            elif self.cropping[1][1] == 0:
                return x[:,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:,
                         self.cropping[2][0]:-self.cropping[2][1],
                         :]
            elif self.cropping[2][1] == 0:
                return x[:,
                         self.cropping[0][0]:-self.cropping[0][1],
                         self.cropping[1][0]:-self.cropping[1][1],
                         self.cropping[2][0]:,
                         :]
            return x[:,
                     self.cropping[0][0]:-self.cropping[0][1],
                     self.cropping[1][0]:-self.cropping[1][1],
                     self.cropping[2][0]:-self.cropping[2][1],
                     :]

    def get_config(self):
        config = {'cropping': self.cropping}
        base_config = super(Cropping3D, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))


# Aliases

Conv1D = Convolution1D
Conv2D = Convolution2D
Conv3D = Convolution3D
Deconv2D = Deconvolution2D
AtrousConv1D = AtrousConvolution1D
AtrousConv2D = AtrousConvolution2D
SeparableConv2D = SeparableConvolution2D
