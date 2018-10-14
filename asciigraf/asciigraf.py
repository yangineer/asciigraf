#############################################################################
# Copyright (c) 2017-present, Opus One Energy Solutions Corporation
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#############################################################################

from collections import OrderedDict
import re

import networkx


def graph_from_ascii(network_string):
    """ Produces a networkx graph, based on an ascii drawing
        of a network
    """
    EDGE_CHAR_NEIGHBOURS = {  # first point in tuple is the point parsed first
        "-":  [Point(-1, 0), Point(1, 0)],
        "\\": [Point(-1, -1),  Point(1, 1)],
        "/":  [Point(1, -1), Point(-1, 1)],
        "|":  [Point(0, -1), Point(0, 1)]
    }
    EDGE_CHARS = {"\\", "-", "/", "|"}
    ascii_nodes = list(node_iter(network_string))

    # First pass to map edge characters
    edge_chars = OrderedDict(
        (pos, char)
        for pos, char in char_iter(network_string)
        if char in EDGE_CHARS
    )

    # Second pass to parse out nodes and labels
    node_chars = OrderedDict()  # of the form {Point -> 'n', Point -> 'o',...}
    label_chars = OrderedDict()  # of the form {Point -> 'l', Point -> 'a',..}
    nodes = OrderedDict()  # of the form {Point -> 'node_name'}
    labels = OrderedDict()  # of the form {Point -> 'label'}
    for ascii_label, root_position in ascii_nodes:
        char_map_update = char_map(ascii_label, root_position)
        if ascii_label.startswith("(") and ascii_label.endswith(")"):
            label_chars.update(char_map_update)
            labels[root_position + Point(1, 0)] = ascii_label[1:-1]
        else:
            node_chars.update(char_map_update)
            nodes[root_position] = ascii_label

    node_char_to_node = map_text_chars_to_text(nodes)
    label_char_to_label = map_text_chars_to_text(labels)

    # Third pass to patch edge characters in where labels were
    for position, label_character in label_chars.items():
        above = position + Point(0, -1)
        below = position + Point(0, 1)
        if label_character == "(":
            left = position + Point(-1, 0)
            if edge_chars.get(left, "") == "-":
                edge_chars[position] = "-"
        elif label_character == ")":
            right = position + Point(1, 0)
            if edge_chars.get(right, "") == "-":
                edge_chars[position] = "-"
        elif edge_chars.get(above, "") == "|" and edge_chars.get(below, "") == "|":
            edge_chars[position] = "|"
        else:
            if edge_chars.get(left, "") == '-':
                edge_chars[position] = '-'

    # we want to process the edges from top->bottom, left->right
    edge_chars = OrderedDict(sorted(edge_chars.items()))

    edge_char_to_edge_map = {}
    edges = []

    for pos, char in edge_chars.items():
        trailing_offset, leading_offset = EDGE_CHAR_NEIGHBOURS[char]
        neighbor = pos + trailing_offset
        neighbor_2 = pos + leading_offset

        # we can skip this position if a previous iteration already
        # mapped the character to an edge
        if pos not in edge_char_to_edge_map:
            if neighbor in edge_char_to_edge_map:  # Add this node to the edge
                edge_char_to_edge_map[pos] = edge_char_to_edge_map[neighbor]
                edge_char_to_edge_map[pos]["points"].append(pos)
            else:  # Make a new edge
                edge_char_to_edge_map[pos] = dict(points=[pos], nodes=[])
                edges.append(edge_char_to_edge_map[pos])

            # we can look ahead at other neighbor and add it too -- this
            # step allows us to solve a few extra corner types
            if (
                neighbor_2 not in edge_char_to_edge_map
                and neighbor_2 in edge_chars
            ):
                edge_char_to_edge_map[neighbor_2] = edge_char_to_edge_map[pos]
                edge_char_to_edge_map[pos]["points"].append(neighbor_2)

        neighboring_nodes = [
            node_char_to_node[pos+pos_offset]
            for pos_offset in EDGE_CHAR_NEIGHBOURS[char]
            if pos+pos_offset in node_chars
        ]
        edge_char_to_edge_map[pos]["nodes"] += neighboring_nodes

    ascii_graph = networkx.OrderedGraph()
    ascii_graph.add_nodes_from(
        (node, {"position": position})
        for position, node in nodes.items()
    )
    for edge in edges:
        if len(edge['nodes']) > 2:
            raise TooManyNodesOnEdge(edge)
        elif len(edge['nodes']) < 2:
            raise TooFewNodesOnEdge(edge)
        else:
            ascii_graph.add_edge(*edge['nodes'])
    networkx.set_edge_attributes(ascii_graph, name="length", values={
        tuple(edge["nodes"]): len(edge["points"])
        for edge in edges if edge["nodes"]
    })
    networkx.set_edge_attributes(
        ascii_graph, name="label",
        values={
            tuple(edge_char_to_edge_map[pos]["nodes"]): label
            for pos, label in label_char_to_label.items()
            if pos in edge_char_to_edge_map
        }
    )
    return ascii_graph


def char_map(text, root_position):
        """ Maps the position of each character in 'text'

            e.g.

            char_map("foo", root_position=Point(20, 2)) -> {
                Point(20, 2) -> 'f',
                Point(21, 2) -> 'o',
                Point(22, 2) -> 'o',
            }
        """
        return OrderedDict(
            (Point(root_position.x+x, root_position.y), char)
            for x, char in enumerate(text)
        )


def map_text_chars_to_text(text_map):
    """ Maps characters in text elements to the text elements

        e.g.

        text_map = {
            Point(1, 2): 'foo',
            Point(3, 4):  'bar',
        }

        map_text_chars_to_text(text_map) -> {
            Point(1, 2): 'foo',
            Point(2, 2): 'foo',
            Point(3, 2): 'foo',
            Point(3, 4): 'bar',
            Point(4, 4): 'bar',
            Point(5, 4): 'bar',
        }
    """
    return OrderedDict(
        (position, text)
        for root_position, text in text_map.items()
        for position, _ in char_map(text, root_position).items()
    )


def find_nodes_and_labels(nodes):
    """ Finds all the nodes and labels in the diagram

         node1-----(label1)-----node2
    """
    node_chars = OrderedDict()
    line_labels = {}
    line_label_char_positions = set()
    for node_label, root_position in nodes:
        node_label_char_positions = {
            root_position + Point(offset, 0)
            for offset, _ in enumerate(node_label)
        }
        if node_label.startswith("(") and node_label.endswith(")"):
            label_value = node_label[1:-1]
            line_labels[root_position] = label_value
            line_label_char_positions |= node_label_char_positions
        else:
            node_chars.update(
                (pos, node_label) for pos in node_label_char_positions
            )

    return node_chars, line_labels, line_label_char_positions


def clean_labels_from_edge_char_map(edge_chars, line_labels):
    # Second pass to correct vertical labels. This needs to be
    # a correction so that the OrderedDict is correctly setup
    for root_position, label in list(line_labels.items()):
        is_vertical_label = any(
            above in edge_chars and edge_chars[above] == '|'
            for above in (
                root_position + Point(i, -1)
                for i, char in enumerate(label)
            )
        )

        if is_vertical_label:
            for i in range(len(label) + 2):  # + 2 for the parentheses
                pos = root_position + Point(i, 0)
                above = pos + Point(0, -1)

                try:
                    if edge_chars[above] == '|':
                        edge_chars[pos] = '|'
                        del line_labels[root_position]
                        line_labels[pos] = label
                    else:
                        del edge_chars[pos]
                except KeyError:
                    # pass
                    del edge_chars[pos]


class Point(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Point(self.x - other.x, self.y - other.y)

    def __iter__(self):
        for el in (self.x, self.y):
            yield el

    def __repr__(self):
        return "Point({}, {})".format(self.x, self.y)

    def __eq__(self, other):
        return (type(self) == type(other) and
                self.x == other.x and
                self.y == other.y
                )

    def __lt__(self, other):
        return self.y < other.y or (
            not self.y > other.y and
            self.x < other.x
        )

    def __hash__(self):
        return hash((self.__class__, self.x, self.y))


def char_iter(network_string):
    return (
        (Point(col, row), char)
        for row, line in enumerate(network_string.split("\n"))
        for col, char in enumerate(line)
        )


def node_iter(network_string):
    for row, line in enumerate(network_string.split("\n")):
        for match in re.finditer('\(?([0-9A-Za-z_{}]+)\)?', line):
            yield (match.group(0), Point(match.start(), row))


class TooManyNodesOnEdge(Exception):
    def __init__(self, edge):
        super(TooManyNodesOnEdge, self).__init__(
            'Too many nodes ({}) found on edge starting at {!r}'.format(
                len(edge['nodes']), edge['points'][0]))


class TooFewNodesOnEdge(Exception):
    def __init__(self, edge):
        super(TooFewNodesOnEdge, self).__init__(
            'Too few nodes ({}) found on edge starting at {!r}'.format(
                len(edge['nodes']), edge['points'][0]))


def map_to_string(char_map, node_chars=None):
    node_chars = node_chars or {}
    node_start_map = OrderedDict()
    for position, node_label in node_chars.items():
        if node_label not in node_start_map:
            node_start_map[node_label] = position
        else:
            if position < node_start_map[node_label]:
                node_start_map[node_label] = position

    all_chars = sorted(
        [*{val: key for key, val in node_start_map.items()}.items(),
         *char_map.items()],
        key=lambda x: x[0]
    )

    string = ""
    cursor = Point(0, 0)
    for position, label in all_chars:
        if cursor.y < position.y:
            string += '\n' * (position.y - cursor.y)
            cursor = Point(0, position.y)
        if cursor.x < position.x:
            string += ' ' * (position.x - cursor.x)
            cursor = Point(*position)
        string += label
        cursor.x += len(label)
    return string
