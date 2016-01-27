# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QlrBrowserDockWidget
                                 A QGIS plugin
 This plugin lets the user browse and open qlr files
                             -------------------
        begin                : 2015-11-26
        git sha              : $Format:%H$
        copyright            : (C) 2015 by Asger Skovbo Petersen, Septima
        email                : asger@septima.dk
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
__author__ = 'asger'

from PyQt4.QtCore import pyqtSlot, QCoreApplication
from qgis.core import QgsProject, QgsLayerDefinition, QgsLayerTreeGroup, QgsLayerTreeLayer
from qgis.gui import QgsMessageBar
import random
import string

class QlrManager():
    customPropertyName = "qlrbrowserid"

    def __init__(self, iface, qlrbrowser):
        self.iface = iface
        self.browser = qlrbrowser

        self.fileSystemItemToLegendNode = dict()
        self.modelIndexBeingAdded = None
        self.removingNode = False

        # Get events whenever layers are added or deleted
        layerTreeRoot = QgsProject.instance().layerTreeRoot()
        layerTreeRoot.addedChildren.connect(self.legend_layersadded)
        layerTreeRoot.removedChildren.connect(self.legend_layersremoved)

        # Get events when user interacts with browser
        self.browser.itemStateChanged.connect(self.browser_itemclicked)

    def syncCheckedItems(self):
        # Loop through our list and update if layers have been removed
        for fileitem, nodes in self.fileSystemItemToLegendNode.items():
            # print "Checking node", nodehandle
            allRemoved = True
            for nodeinfo in nodes:
                node = self._getlayerTreeNode(nodeinfo)
                if node is not None:
                    allRemoved = False
                    break
            if allRemoved:
                self.browser.setPathCheckState(fileitem, False)
                self.fileSystemItemToLegendNode.pop(fileitem, None)

    def legend_layersremoved(self, node, indexFrom, indexTo):
        #print "REMOVED", node, indexFrom, indexTo
        # Ignore, if we removed this node
        if self.removingNode:
            #print "We removed this node our self"
            return
        self.syncCheckedItems()

    def legend_layersadded(self, node, indexFrom, indexTo):
        #print "WILL ADDXXXX", node, indexFrom, indexTo
        # Are nodes being added by us?
        if self.modelIndexBeingAdded:
            # node is added by us. (Can potentially be many unnested layers)
            nodes = []
            for index in range(indexFrom, indexTo + 1):
                internalid = self._random_string()
                nodeinfo = {'internalid': internalid}
                addedNode = node.children()[index]
                addedNode.setCustomProperty(QlrManager.customPropertyName, internalid)
                if isinstance(addedNode, QgsLayerTreeGroup):
                    nodeinfo['type'] = 'group'
                    nodeinfo['name'] = addedNode.name()
                elif isinstance(addedNode, QgsLayerTreeLayer):
                    nodeinfo['type'] = 'layer'
                    nodeinfo['name'] = addedNode.layerName()
                    nodeinfo['layerid'] = addedNode.layerId()
                nodes.append(nodeinfo)
            #print "Adding layer", mapping
            self.fileSystemItemToLegendNode[self.modelIndexBeingAdded] = nodes
            self.modelIndexBeingAdded = None
        # print self.fileSystemItemToLegendNode

    @pyqtSlot(object, int)
    def browser_itemclicked(self, fileinfo, newState):
        # print "qlrmanager itemclicked", fileinfo
        path = fileinfo.fullpath
        if newState == False:
            # Item was unchecked. Remove node(s)
            if self.fileSystemItemToLegendNode.has_key(path):
                nodes = self.fileSystemItemToLegendNode[path]
                #print "Remove node", nodehandle
                for nodeinfo in nodes:
                    node = self._getlayerTreeNode(nodeinfo)
                    if node:
                        try:
                            self.removingNode = True
                            node.parent().removeChildNode(node)
                        finally:
                            self.removingNode = False
                self.fileSystemItemToLegendNode.pop(path, None)
        else:
            # Item was checked
            if fileinfo.isdir:
                pass
            else:
                try:
                    # This is used by our self to signal (to ourselves) that we are in the process of adding a layer now
                    self.modelIndexBeingAdded = path
                    msgWidget = self.iface.messageBar().createMessage(u"Indlæser", fileinfo.displayname)
                    msgItem = self.iface.messageBar().pushWidget(msgWidget, QgsMessageBar.INFO, duration=0)
                    # Force show messageBar
                    QCoreApplication.processEvents()
                    # Load qlr
                    QgsLayerDefinition.loadLayerDefinition(path, self.layer_insertion_point())
                    # This is backwards, but qlr is always loaded at the bottom of the TOC
                    self._move_qlr_to_top(path)
                    # Remove message
                    self.iface.messageBar().popWidget(msgItem)
                finally:
                    self.modelIndexBeingAdded = None

    def layer_insertion_point(self):
        # At the moment just return root
        root = QgsProject.instance().layerTreeRoot()
        return root

    def _move_qlr_to_top(self, qlrpath):
        """Moves the layers added to the TOC from the given QLR file. For now always to the top of the TOC"""
        # Only supports moving layer to the top of the TOC.
        for nodeinfo in self.fileSystemItemToLegendNode[qlrpath]:
            node = self._getlayerTreeNode(nodeinfo)
            self._move_toc_layer(node)

    def _move_toc_layer(self, node):
        # See http://gis.stackexchange.com/questions/134284/how-to-move-layers-in-the-qgis-table-of-contents-via-pyqgis
        # Clone and insert at right place
        myClone = node.clone()
        treeRoot = QgsProject.instance().layerTreeRoot()
        treeRoot.insertChildNode(0, myClone)
        # Delete old
        parent = node.parent()
        parent.removeChildNode(node)

    def _random_string(self):
        return ''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(32)])

    def _getgroupNodes(self, rootNode):
        groupnodes = []
        for n in rootNode.children():
            #print "Checking node", n
            if isinstance(n, QgsLayerTreeGroup):
                #print n, "is a group node"
                groupnodes.append(n)
                groupnodes += self._getgroupNodes(n)
        #print "all group nodes", groupnodes
        return groupnodes

    def _getlayerTreeNode(self, nodeinfo):
        root = QgsProject.instance().layerTreeRoot()
        if nodeinfo['type'] == 'layer':
            node = root.findLayer( nodeinfo['layerid'] )
            return node
        elif nodeinfo['type'] == 'group':
            for n in self._getgroupNodes(root):
                #print "is ", n, "our group node?"
                internalid = n.customProperty(QlrManager.customPropertyName)
                #print "properties", n.customProperties()
                #print "internalid", internalid
                if internalid == nodeinfo['internalid']:
                    return n
            # if we reach here we didnt find the group
            return None
        else:
            raise Exception("Wrong type")

    def unload(self):
        layerTreeRoot = QgsProject.instance().layerTreeRoot()
        layerTreeRoot.addedChildren.disconnect(self.legend_layersadded)
        layerTreeRoot.removedChildren.disconnect(self.legend_layersremoved)

        # Get events when user interacts with browser
        self.browser.itemStateChanged.disconnect(self.browser_itemclicked)