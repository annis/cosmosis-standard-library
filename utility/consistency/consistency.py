"""
This module provides a mechanism to both ensure consistency between
and "fill-in-the-blanks" in sets of parameters.

For example, there are various ways to specify cosmological
parameters - Omega_m vs Omega_m * h^2, Omega_b versus baryon fraction,
omega_lambda, omega_k, etc.

You can check that a set of parameters
a) is consistent
b) contains enough information to specify all other parameters

using this module like so:
> consistency = cosmology_consistency()
> p = {"omega_m":0.3, "hubble":72, ... }
q = consistency(p)

This will raise an error if the cosmology is over- or under-specified,
depending what is in the p dictionary, and if not will return q with the
remaining parameters filled in.

This incorporates a series of escalating assumptions.
At first, no other data is assumed.  If this model is under-specified,
we then try using omega_nu=0 as well.  And if that fails we escalate to
using both omega_nu=0 and omega_k=0.

The relations between parameters and the assumptions
can all be specified directly instead of using the cosmology examples
here. See the global variables for the structure.


"""

from numpy import nan, isnan, allclose

def cosmology_consistency(verbose=False):
	return Consistency(COSMOLOGY_CONSISTENCY_RELATIONS, COSMOLOGY_POSSIBLE_DEFAULTS, verbose)

COSMOLOGY_CONSISTENCY_RELATIONS = [
	("omega_m", "ommh2/h0/h0"),
	("omega_b", "ombh2/h0/h0"),
	("omega_c", "omch2/h0/h0"),
	("omega_nu", "omnuh2/h0/h0"),
	("ommh2", "omega_m*h0*h0"),
	("ombh2", "omega_b*h0*h0"),
	("omch2", "omega_c*h0*h0"),
	("omnuh2", "omega_nu*h0*h0"),
	("omch2", "ommh2-ombh2"),
	("ommh2", "omch2+ombh2"),
	("baryon", "omega_b/omega_m"),
	("omega_b", "omega_m*baryon_fraction"),
	("omega_m", "omega_b/baryon_fraction"),
	("baryon_fraction", "ombh2/ommh2"),
	("ombh2", "ommh2*baryon_fraction"),
	("ommh2", "ombh2/baryon_fraction"),
	("omega_m", "omega_b+omega_c"),
	("h0", "(ommh2/omega_m)**0.5"),
	("h0", "(ombh2/omega_b)**0.5"),
	("h0", "(omch2/omega_c)**0.5"),
	#Had to leave this one out as it causes ZeroDivisionError.
	#Could catch this somewhere?
	# ("h0", "(omnuh2/omega_nu)**0.5"),
	("h0","hubble/100"),
	("hubble", "h0*100"),
	("omega_lambda", "1-omega_m-omega_k-omega_nu"),
	("omega_m", "1-omega_lambda-omega_k-omega_nu"),
	("omega_k", "1-omega_m-omega_lambda-omega_nu"),
	("omega_nu", "1-omega_m-omega_lambda-omega_k"),
]

COSMOLOGY_POSSIBLE_DEFAULTS = [
	("omega_nu", 0.0),
	("omega_k", 0.0),
]

class PoorlySpecifiedModel(ValueError):
	pass

class OverSpecifiedModel(PoorlySpecifiedModel):
	pass

class UnderSpecifiedModel(PoorlySpecifiedModel):
	pass

class Consistency(object):
	def __init__(self, relations, possible_defaults, verbose=False):
		self.relations = relations
		self.parameters = {}
		self.possible_defaults = possible_defaults
		self.verbose=verbose
		self.reset()

	def __call__(self, parameters):
		#First we try specifiying as little as possible,
		#without using any of the default values.
		#Then we gradually start using more of the defaults
		#until (hopefully) we have a fully-specified model.
		for i in xrange(len(self.possible_defaults)):
			try:
				defaults = self.possible_defaults[:i]
				if self.verbose and i>0:
					text = ", ".join(["%s=%g"%d for d in defaults])
					print
					print "Trying assumptions: ", text
				q = self.run_with_defaults(parameters, defaults)
				if self.verbose:
					print "Model okay"
				return q
			except UnderSpecifiedModel:
				#It is possible that this model will not
				#be fully specified.  That's okay - we'll
				#just try throwing some more defaults in.
				if self.verbose:
					unspecified = self.find_unspecified()
					print "Model still unspecified: %s" % (", ".join(unspecified))
		#Our final run uses all the defaults we know about.
		#If this still doesn't work we'll throw the error.
		if self.verbose and self.possible_defaults:
			text = ", ".join(["%s=%g"%d for d in self.possible_defaults])
			print
			print "Trying assumptions: ", text
		q = self.run_with_defaults(parameters, self.possible_defaults)
		if self.verbose:
			print "Model okay."
		return q

	def run_with_defaults(self, parameters, defaults):
		#Set initially know parameters
		self.reset()
		self.parameters.update(parameters)
		for name,value in defaults:
			self.parameters[name] = value

		#Loop repeatedly through the model
		#checking for parameters we can compute.
		#The max number of loops is the number of relations,
		#since we cannot possibly do anything more after that
		for i in xrange(1+len(self.relations)):
			#Apply all the relations to calculate 
			#new values
			for relation in self.relations:
				self.apply_relation(relation)
			#check for still unspecified values.
			#if there are none then we are done.
			unspecified=self.find_unspecified()
			if not unspecified:
				break
		else:
			#This happens if we never break from the loop.
			#In that case we must never have fully specified the model
			raise UnderSpecifiedModel("Model under-specified - I could not compute"
				"these values: %r"%unspecified)
		#output results
		return self.parameters.copy()

	def reset(self):
		#Reset all parmeters to nan, which indicates
		#unspecified
		for name,function in self.relations:
			self.parameters[name] = nan


	def apply_relation(self, relation):
		name, function = relation
		#Try computing this parameter from the relation.
		#If any of its inputs are unspecified then
		#it will also be unspecified.
		value = eval(function, None, self.parameters)
		if isnan(value):
			#We do not yet have enough information to determine this
			#parameter
			return
		current_value = self.parameters[name]
		if isnan(current_value):
			#This parameter has not yet been computed.
			#so we now have it and can fill it in.
			self.parameters[name] = value
			if self.verbose:
				print "Calculated %s = %g from %s" % (name, value, function)
		else:
			#This parameter has already been calculated or specified.
			#So we check for consistency
			if not allclose(current_value, value):
				raise OverSpecifiedModel("Model over-specified and consistency relations failed"
					"for parameter %s (values %g and %g)"%(name,current_value,value))

	def find_unspecified(self):
		#Check for any nan parameters
		unspecified = []
		for name,value in self.parameters.items():
			#We use nan to signal "unspecified"
			#since it is infectious
			if isnan(value):
				unspecified.append(name)
		return unspecified





# Some tests, probably not complete:
def test_under_specified():
	import nose
	consistency = cosmology_consistency()
	p = {"omega_m":0.3, "hubble":72.}
	nose.tools.assert_raises(UnderSpecifiedModel, consistency, p)

def test_defaults():
	import nose
	consistency = cosmology_consistency()
	p = {"omega_m":0.3, "hubble":72., "baryon_fraction":0.02}
	q = consistency(p)

def test_fully_specified():
	consistency = cosmology_consistency()
	p = {"omega_m":0.3, "hubble":72., "omega_b":0.04, "omega_k":0.0}
	q = consistency(p)
	r = consistency(q)
	assert q==r

def test_rerun():
	consistency = cosmology_consistency()
	p = {"omega_m":0.3, "hubble":72., "omega_b":0.04, "omega_k":0.0}
	p1 = consistency(p)
	p2 = consistency(p)
	assert p1==p2

def test_over_specified():
	import nose
	consistency = cosmology_consistency()
	p = {"omega_m":0.3, "hubble":72., "omega_b":0.04, "omega_c":0.1}
	nose.tools.assert_raises(OverSpecifiedModel, consistency, p)
