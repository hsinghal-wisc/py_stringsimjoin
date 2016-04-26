import pandas as pd
import pyprind

from py_stringsimjoin.filter.filter import Filter
from py_stringsimjoin.filter.filter_utils import get_prefix_length
from py_stringsimjoin.index.prefix_index import PrefixIndex
from py_stringsimjoin.utils.helper_functions import \
                                                 get_output_header_from_tables
from py_stringsimjoin.utils.helper_functions import get_output_row_from_tables
from py_stringsimjoin.utils.token_ordering import gen_token_ordering_for_lists
from py_stringsimjoin.utils.token_ordering import gen_token_ordering_for_tables
from py_stringsimjoin.utils.token_ordering import order_using_token_ordering


class PrefixFilter(Filter):
    """Prefix filter class.

    Attributes:
        tokenizer: Tokenizer function, which is used to tokenize input string.
        sim_measure_type: String, similarity measure type.
        threshold: float, similarity threshold to be used by the filter.
    """
    def __init__(self, tokenizer, sim_measure_type, threshold):
        self.tokenizer = tokenizer
        self.sim_measure_type = sim_measure_type
        self.threshold = threshold
        super(self.__class__, self).__init__()

    def filter_pair(self, lstring, rstring):
        """Filter two strings with prefix filter.

        Args:
        lstring, rstring : input strings

        Returns:
        result : boolean, True if the tuple pair is dropped.
        """
        # check for empty string
        if (not lstring) or (not rstring):
            return True

        ltokens = list(set(self.tokenizer(lstring)))
        rtokens = list(set(self.tokenizer(rstring)))

        token_ordering = gen_token_ordering_for_lists([ltokens, rtokens])
        ordered_ltokens = order_using_token_ordering(ltokens, token_ordering)
        ordered_rtokens = order_using_token_ordering(rtokens, token_ordering)

        l_prefix_length = get_prefix_length(len(ordered_ltokens),
                                            self.sim_measure_type,
                                            self.threshold) 
        r_prefix_length = get_prefix_length(len(ordered_rtokens),
                                            self.sim_measure_type,
                                            self.threshold)
        prefix_overlap = set(ordered_ltokens[0:l_prefix_length]).intersection(
                         set(ordered_rtokens[0:r_prefix_length]))

        if len(prefix_overlap) > 0:
            return False
        else:
            return True

    def filter_tables(self, ltable, rtable,
                      l_key_attr, r_key_attr,
                      l_filter_attr, r_filter_attr,
                      l_out_attrs=None, r_out_attrs=None,
                      l_out_prefix='l_', r_out_prefix='r_'):
        """Filter tables with prefix filter.

        Args:
        ltable, rtable : Pandas data frame
        l_key_attr, r_key_attr : String, key attribute from ltable and rtable
        l_filter_attr, r_filter_attr : String, filter attribute from ltable and rtable
        l_out_attrs, r_out_attrs : list of attribtues to be included in the output table from ltable and rtable
        l_out_prefix, r_out_prefix : String, prefix to be used in the attribute names of the output table 

        Returns:
        result : Pandas data frame
        """
        # find column indices of key attr, filter attr and output attrs in ltable
        l_columns = list(ltable.columns.values)
        l_key_attr_index = l_columns.index(l_key_attr)
        l_filter_attr_index = l_columns.index(l_filter_attr)
        l_out_attrs_indices = []
        if l_out_attrs is not None:
            for attr in l_out_attrs:
                l_out_attrs_indices.append(l_columns.index(attr))        

        # find column indices of key attr, filter attr and output attrs in rtable
        r_columns = list(rtable.columns.values)
        r_key_attr_index = r_columns.index(r_key_attr)
        r_filter_attr_index = r_columns.index(r_filter_attr)
        r_out_attrs_indices = []
        if r_out_attrs:
            for attr in r_out_attrs:
                r_out_attrs_indices.append(r_columns.index(attr))
        
        # build a dictionary on ltable
        ltable_dict = {}
        for l_row in ltable.itertuples(index=False):
            ltable_dict[l_row[l_key_attr_index]] = l_row

        # build a dictionary on rtable
        rtable_dict = {}
        for r_row in rtable.itertuples(index=False):
            rtable_dict[r_row[r_key_attr_index]] = r_row

        # generate token ordering using tokens in l_filter_attr
        # and r_filter_attr
        token_ordering = gen_token_ordering_for_tables(
                                            [ltable_dict.values(),
                                             rtable_dict.values()],
                                            [l_filter_attr_index,
                                             r_filter_attr_index],
                                            self.tokenizer)

        # Build prefix index on l_filter_attr
        prefix_index = PrefixIndex(ltable_dict.values(),
                                   l_key_attr_index, l_filter_attr_index,
                                   self.tokenizer, self.sim_measure_type,
                                   self.threshold, token_ordering)
        prefix_index.build()

        output_rows = []
        has_output_attributes = (l_out_attrs is not None or
                                 r_out_attrs is not None)
        prog_bar = pyprind.ProgBar(len(rtable.index))
        candset_id = 1

        for r_row in rtable_dict.values():
            r_id = r_row[r_key_attr_index]
            r_string = str(r_row[r_filter_attr_index])
            # check for empty string
            if not r_string:
                continue
            r_filter_attr_tokens = set(self.tokenizer(r_string))
            r_ordered_tokens = order_using_token_ordering(r_filter_attr_tokens,
                                                          token_ordering)
           
            r_prefix_length = get_prefix_length(len(r_ordered_tokens),
                                                self.sim_measure_type,
                                                self.threshold)

            # probe prefix index and find candidates
            candidates = set()
            for token in r_ordered_tokens[0:r_prefix_length]:
                for cand in prefix_index.probe(token):
                    candidates.add(cand)

            for cand in candidates:
                if has_output_attributes:
                    output_row = get_output_row_from_tables(
                                     candset_id,
                                     ltable_dict[cand], r_row,
                                     cand, r_id, 
                                     l_out_attrs_indices, r_out_attrs_indices)
                    output_rows.append(output_row)
                else:
                    output_rows.append([candset_id, cand, r_id])

                candset_id += 1
 
            prog_bar.update()

        output_header = get_output_header_from_tables(
                            '_id',
                            l_key_attr, r_key_attr,
                            l_out_attrs, r_out_attrs, 
                            l_out_prefix, r_out_prefix)

        # generate a dataframe from the list of output rows
        output_table = pd.DataFrame(output_rows, columns=output_header)
        return output_table
