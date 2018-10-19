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

    nodes, labels = map_nodes_and_labels(network_string)

    edge_chars = map_edge_chars(network_string)
    patch_edge_chars_over_labels(labels, edge_chars)

    # need to sort it so the patched-in edge chars will be in order
    edge_chars = OrderedDict(sorted(edge_chars.items()))

    node_char_to_node = map_text_chars_to_text(nodes)
    label_char_to_label = map_text_chars_to_text(labels)

    edge_char_to_edge_map = {}  # {Point -> {"points": [], "nodes": []}}
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
        (node, {"position": position}) for position, node in nodes.items()
    )
    ascii_graph.add_edges_from(
        (*edge['nodes'], {"length": len(edge["points"])})
        for edge in edges
    )
    networkx.set_edge_attributes(
        ascii_graph, name="label",
        values={
            tuple(edge_char_to_edge_map[pos]["nodes"]): label[1:-1]
            for pos, label in label_char_to_label.items()
            if pos in edge_char_to_edge_map
        }
    )
    return ascii_graph


def map_nodes_and_labels(network_string):
    """ Map the root position of nodes and labels
        to the node / label text.

        e.g. map_nodes_and_labels("  n1--(label1)--n2  ") -> {
            Point(2, 0): "n1",
            Point(6, 0): "(label1)",
            Point(16, 0): "n2",
        }
    """
    ascii_nodes = list(node_iter(network_string))
    nodes = OrderedDict()  # of the form {Point -> 'node_name'}
    labels = OrderedDict()  # of the form {Point -> 'label'}
    for ascii_label, root_position in ascii_nodes:
        if ascii_label.startswith("(") and ascii_label.endswith(")"):
            labels[root_position] = ascii_label
        else:
            nodes[root_position] = ascii_label
    return nodes, labels


def patch_edge_chars_over_labels(labels, edge_chars):
    """ Adds in edge chars where labels crossed an edge

        e.g.

        ---(horizontal_label)---

                becomes

        ------------------------

        e.g.
                |                         |
          (vertical_label)   becomes      |
                |                         |
    """

    label_chars = OrderedDict(
        (root_position + Point(i, 0), char)
        for root_position, label in labels.items()
        for i, char in enumerate(label)
    )
    for position, label_character in label_chars.items():
        above = position + Point(0, -1)
        below = position + Point(0, 1)
        left = position + Point(-1, 0)
        right = position + Point(1, 0)

        if label_character == "(":
            if edge_chars.get(left, "") == "-":
                edge_chars[position] = "-"
        elif label_character == ")":
            if edge_chars.get(right, "") == "-":
                edge_chars[position] = "-"
        elif edge_chars.get(above, "") == "|" and edge_chars.get(below, "") == "|":
            edge_chars[position] = "|"
        else:
            if edge_chars.get(left, "") == '-':
                edge_chars[position] = '-'


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


def map_edge_chars(network_string):
    """ Map positions in the string to edge chars

        e.g. map_edge_chars("  --|   ") -> {
            Point(3,0): "-",
            Point(4,0): "-",
            Point(5,0): "|",
        }
    """
    return OrderedDict(
        (Point(col, row), char)
        for row, line in enumerate(network_string.split("\n"))
        for col, char in enumerate(line)
        if char in EDGE_CHARS
    )


def node_iter(network_string):
    for row, line in enumerate(network_string.split("\n")):
        for match in re.finditer('\(?([0-9A-Za-z_{}]+)\)?', line):
            yield (match.group(0), Point(match.start(), row))




def map_to_string(char_map, node_chars=None):
    """ Redraws a char_map and node_char map """
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

EDGE_CHARS = {"\\", "-", "/", "|"}

LEFT, RIGHT = Point(-1, 0), Point(1, 0)
ABOVE, BELOW = Point(0, -1), Point(0, 1)
TOP_LEFT, BOTTOM_RIGHT = Point(-1, -1), Point(1, 1)
BOTTOM_LEFT, TOP_RIGHT = Point(1, -1), Point(-1, 1)
