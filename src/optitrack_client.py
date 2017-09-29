# This file is originally based on the sample code in NatNetClient.py
# provided with the NatNetSDK.  It has been converted to Python 2,
# threading has been removed, along with various other modifications.

import argparse
import select
import socket
import struct
import time

import lcm

from optitrack import optitrack_data_descriptions_t
from optitrack import optitrack_frame_t
from optitrack import optitrack_marker_set_description_t
from optitrack import optitrack_marker_set_t
from optitrack import optitrack_marker_t
from optitrack import optitrack_rigid_body_t
from optitrack import optitrack_rigid_body_description_t

def trace( *args ):
    pass
    #print "".join(map(str,args))

# Create structs for reading various object types to speed up parsing.
Vector3 = struct.Struct( '<fff' )
Quaternion = struct.Struct( '<ffff' )
FloatValue = struct.Struct( '<f' )
DoubleValue = struct.Struct( '<d' )
Int32Value = struct.Struct( '<i' )
Int16Value = struct.Struct( '<h' )

class NatNetClient:
    def __init__( self, options ):
        self.options = options
        # Change this value to force the IP address of the NatNet
        # server.
        self.serverIPAddress = None

        # NatNet Command channel
        self.commandPort = 1510

        # NatNet Data channel
        self.dataPort = 1511

        # NatNet stream version. This will be updated to the actual version the server is using during initialization.
        self.__natNetStreamVersion = (3,0,0,0)

        self.lc = lcm.LCM()

    # Client/server message ids
    NAT_PING                  = 0
    NAT_PINGRESPONSE          = 1
    NAT_REQUEST               = 2
    NAT_RESPONSE              = 3
    NAT_REQUEST_MODELDEF      = 4
    NAT_MODELDEF              = 5
    NAT_REQUEST_FRAMEOFDATA   = 6
    NAT_FRAMEOFDATA           = 7
    NAT_MESSAGESTRING         = 8
    NAT_DISCONNECT            = 9
    NAT_UNRECOGNIZED_REQUEST  = 100

    # Create a data socket to attach to the NatNet stream
    def __createDataSocket( self, port ):
        result = socket.socket( socket.AF_INET,     # Internet
                              socket.SOCK_DGRAM,
                              socket.IPPROTO_UDP)    # UDP
        result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        result.bind( ('', port) )

        if self.options.local_address == '':
            mreq = struct.pack("4sl",
                               socket.inet_aton(self.options.multicast_address),
                               socket.INADDR_ANY)
            result.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        else:
            result.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                              socket.inet_aton(self.options.multicast_address) +
                              socket.inet_aton(self.options.local_address))

        return result

    # Create a command socket to attach to the NatNet stream
    def __createCommandSocket( self ):
        result = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )
        result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        result.bind( ('', 0) )
        result.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        return result

    # Unpack a rigid body object from a data packet.  Returns a tuple
    # of the offset and an optitrack_rigid_body_t LCM message.
    def __unpackRigidBody( self, data ):
        offset = 0
        msg = optitrack_rigid_body_t()

        # ID (4 bytes)
        msg.id, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "ID:", msg.id )

        # Position and orientation
        pos = Vector3.unpack( data[offset:offset+12] )
        offset += 12
        trace( "\tPosition:", pos[0],",", pos[1],",", pos[2] )
        msg.xyz = pos

        rot = Quaternion.unpack( data[offset:offset+16] )
        offset += 16
        trace( "\tOrientation:", rot[0],",", rot[1],",", rot[2],",", rot[3] )
        msg.quat = rot

        # Marker count (4 bytes)
        markerCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        markerCountRange = range( 0, markerCount )
        trace( "\tMarker Count:", markerCount )
        msg.num_markers = markerCount

        # Marker positions
        for i in markerCountRange:
            pos = Vector3.unpack( data[offset:offset+12] )
            offset += 12
            trace( "\tMarker", i, ":", pos[0],",", pos[1],",", pos[2] )
            msg.marker_xyz.append(pos)
            # Populate marker_ids and marker_sizes in case we
            # don't fill them later.

            msg.marker_ids.append(i)
            msg.marker_sizes.append(0.)


        if( self.__natNetStreamVersion[0] >= 2 ):
            # Marker ID's
            for i in markerCountRange:
                msg.marker_ids[i], = Int32Value.unpack(data[offset:offset + 4])
                offset += 4
                trace( "\tMarker ID", i, ":", msg.marker_ids[i] )

            # Marker sizes
            for i in markerCountRange:
                msg.marker_sizes[i], = FloatValue.unpack( data[offset:offset+4] )
                offset += 4
                trace( "\tMarker Size", i, ":", msg.marker_sizes[i] )

            markerError, = FloatValue.unpack( data[offset:offset+4] )
            offset += 4
            trace( "\tMarker Error:", markerError )
            msg.mean_error = markerError

        # Version 2.6 and later
        if( ( ( self.__natNetStreamVersion[0] == 2 ) and ( self.__natNetStreamVersion[1] >= 6 ) ) or self.__natNetStreamVersion[0] > 2 or self.__natNetStreamVersion[0] == 0 ):
            param, = struct.unpack( 'h', data[offset:offset+2] )
            trackingValid = ( param & 0x01 ) != 0
            offset += 2
            trace( "\tTracking Valid:", 'True' if trackingValid else 'False' )
            msg.params = param

        return offset, msg

    # Unpack a skeleton object from a data packet
    def __unpackSkeleton( self, data ):
        offset = 0

        id, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "ID:", id )

        rigidBodyCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "Rigid Body Count:", rigidBodyCount )
        for j in range( 0, rigidBodyCount ):
            (extra_offset, _) = self.__unpackRigidBody( data[offset:] )
            offset += extra_offset

        return offset

    # Unpack data from a motion capture frame message
    def __unpackMocapData( self, data ):
        trace( "Begin MoCap Frame\n-----------------\n" )

        msg = optitrack_frame_t()
        msg.utime = time.time() * 1e6

        # TODO(sam.creasey) I don't know if this is worth it...
        #data = memoryview( data )
        offset = 0

        # Frame number (4 bytes)
        msg.frame, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "Frame #:", msg.frame )

        # Marker set count (4 bytes)
        markerSetCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "Marker Set Count:", markerSetCount )
        msg.num_marker_sets = markerSetCount

        for i in range( 0, markerSetCount ):
            marker_set = optitrack_marker_set_t()
            # Model name
            #modelName, separator, remainder = bytes(data[offset:]).partition( b'\0' )
            modelName = data[offset:].split('\0')[0]
            offset += len( modelName ) + 1
            trace( "Model Name:", modelName.decode( 'utf-8' ) )
            marker_set.name = modelName

            # Marker count (4 bytes)
            markerCount, = Int32Value.unpack(data[offset:offset + 4])
            offset += 4
            trace( "Marker Count:", markerCount )
            marker_set.num_markers = markerCount

            for j in range( 0, markerCount ):
                marker_set.xyz.append(Vector3.unpack( data[offset:offset+12] ))
                offset += 12
                #trace( "\tMarker", j, ":", pos[0],",", pos[1],",", pos[2] )
            msg.marker_sets.append(marker_set)

        # Unlabeled markers count (4 bytes)
        unlabeledMarkersCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "Unlabeled Markers Count:", unlabeledMarkersCount )
        msg.num_other_markers = unlabeledMarkersCount

        for i in range( 0, unlabeledMarkersCount ):
            pos = Vector3.unpack( data[offset:offset+12] )
            offset += 12
            trace( "\tMarker", i, ":", pos[0],",", pos[1],",", pos[2] )
            msg.other_markers.append(pos)

        # Rigid body count (4 bytes)
        rigidBodyCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        trace( "Rigid Body Count:", rigidBodyCount )
        msg.num_rigid_bodies = rigidBodyCount

        for i in range( 0, rigidBodyCount ):
            (extra_offset, rigid_body_msg) = self.__unpackRigidBody( data[offset:] )
            offset += extra_offset
            msg.rigid_bodies.append(rigid_body_msg)

        # Version 2.1 and later
        skeletonCount = 0
        if( ( self.__natNetStreamVersion[0] == 2 and self.__natNetStreamVersion[1] > 0 ) or self.__natNetStreamVersion[0] > 2 ):
            skeletonCount, = Int32Value.unpack(data[offset:offset + 4])
            offset += 4
            trace( "Skeleton Count:", skeletonCount )
            for i in range( 0, skeletonCount ):
                offset += self.__unpackSkeleton( data[offset:] )

        # Labeled markers (Version 2.3 and later)
        labeledMarkerCount = 0
        if( ( self.__natNetStreamVersion[0] == 2 and self.__natNetStreamVersion[1] > 3 ) or self.__natNetStreamVersion[0] > 2 ):
            labeledMarkerCount, = Int32Value.unpack(data[offset:offset + 4])
            offset += 4
            trace( "Labeled Marker Count:", labeledMarkerCount )
            msg.num_labeled_markers = labeledMarkerCount

            for i in range( 0, labeledMarkerCount ):
                marker = optitrack_marker_t()
                marker.id, = Int32Value.unpack(data[offset:offset + 4])
                offset += 4
                marker.xyz = Vector3.unpack( data[offset:offset+12] )
                offset += 12
                marker.size, = FloatValue.unpack( data[offset:offset+4] )
                offset += 4

                # Version 2.6 and later
                if( ( self.__natNetStreamVersion[0] == 2 and self.__natNetStreamVersion[1] >= 6 ) or self.__natNetStreamVersion[0] > 2 or major == 0 ):
                    param, = struct.unpack( 'h', data[offset:offset+2] )
                    offset += 2
                    occluded = ( param & 0x01 ) != 0
                    pointCloudSolved = ( param & 0x02 ) != 0
                    modelSolved = ( param & 0x04 ) != 0
                    marker.params = param
                msg.labeled_markers.append(marker)

        # Force Plate data (version 2.9 and later)
        if( ( self.__natNetStreamVersion[0] == 2 and self.__natNetStreamVersion[1] >= 9 ) or self.__natNetStreamVersion[0] > 2 ):
            forcePlateCount, = Int32Value.unpack(data[offset:offset + 4])
            offset += 4
            trace( "Force Plate Count:", forcePlateCount )
            for i in range( 0, forcePlateCount ):
                # ID
                forcePlateID, = Int32Value.unpack(data[offset:offset + 4])
                offset += 4
                trace( "Force Plate", i, ":", forcePlateID )

                # Channel Count
                forcePlateChannelCount, = Int32Value.unpack(data[offset:offset + 4])
                offset += 4

                # Channel Data
                for j in range( 0, forcePlateChannelCount ):
                    trace( "\tChannel", j, ":", forcePlateID )
                    forcePlateChannelFrameCount, = Int32Value.unpack(data[offset:offset + 4])
                    offset += 4
                    for k in range( 0, forcePlateChannelFrameCount ):
                        forcePlateChannelVal, = Int32Value.unpack(data[offset:offset + 4])
                        offset += 4
                        trace( "\t\t", forcePlateChannelVal )

        # Latency
        msg.latency, = FloatValue.unpack( data[offset:offset+4] )
        offset += 4

        # Timecode
        msg.timecode, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        msg.timecode_subframe, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4

        # Timestamp (increased to double precision in 2.7 and later)
        if( ( self.__natNetStreamVersion[0] == 2 and self.__natNetStreamVersion[1] >= 7 ) or self.__natNetStreamVersion[0] > 2 ):
            msg.timestamp, = DoubleValue.unpack( data[offset:offset+8] )
            offset += 8
        else:
            msg.timestamp, = FloatValue.unpack( data[offset:offset+4] )
            offset += 4

        # Frame parameters
        param, = struct.unpack( 'h', data[offset:offset+2] )
        isRecording = ( param & 0x01 ) != 0
        trackedModelsChanged = ( param & 0x02 ) != 0
        offset += 2
        msg.params = param
        self.lc.publish('OPTITRACK_FRAMES', msg.encode())

    # Unpack a marker set description packet
    def __unpackMarkerSetDescription( self, data ):
        offset = 0
        description = optitrack_marker_set_description_t()

        name, separator, remainder = bytes(data[offset:]).partition( b'\0' )
        offset += len( name ) + 1
        trace( "Markerset Name:", name.decode( 'utf-8' ) )
        description.name = name

        markerCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        description.num_markers = markerCount;

        for i in range( 0, markerCount ):
            marker_name, separator, remainder = bytes(data[offset:]).partition( b'\0' )
            offset += len( marker_name ) + 1
            trace( "\tMarker Name:", marker_name.decode( 'utf-8' ) )
            description.marker_names.append(marker_name)

        return offset, description

    # Unpack a rigid body description packet
    def __unpackRigidBodyDescription( self, data ):
        offset = 0
        description = optitrack_rigid_body_description_t()

        # Version 2.0 or higher
        if( self.__natNetStreamVersion[0] >= 2 ):
            name, separator, remainder = bytes(data[offset:]).partition( b'\0' )
            offset += len( name ) + 1
            trace( "\tRigid Body Name:", name.decode( 'utf-8' ) )
            description.name = name

        description.id, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4

        description.parent_id, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4

        description.offset_xyz = Vector3.unpack( data[offset:offset+12] )
        offset += 12

        return offset, description

    # Unpack a skeleton description packet
    def __unpackSkeletonDescription( self, data ):
        offset = 0

        name, separator, remainder = bytes(data[offset:]).partition( b'\0' )
        offset += len( name ) + 1
        trace( "\tSkeleton Name:", name.decode( 'utf-8' ) )

        id, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4

        rigidBodyCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4

        for i in range( 0, rigidBodyCount ):
            offset += self.__unpackRigidBodyDescription( data[offset:] )

        return offset

    # Unpack a data description packet
    def __unpackDataDescriptions( self, data ):
        offset = 0
        datasetCount, = Int32Value.unpack(data[offset:offset + 4])
        offset += 4
        data_descriptions = optitrack_data_descriptions_t()

        for i in range( 0, datasetCount ):
            type, = Int32Value.unpack(data[offset:offset + 4])
            offset += 4
            if( type == 0 ):
                count, description = self.__unpackMarkerSetDescription( data[offset:] )
                offset += count
                data_descriptions.marker_sets.append(description)
            elif( type == 1 ):
                count, description = self.__unpackRigidBodyDescription( data[offset:] )
                offset += count
                data_descriptions.rigid_bodies.append(description)
            elif( type == 2 ):
                offset += self.__unpackSkeletonDescription( data[offset:] )

        data_descriptions.num_marker_sets = len(data_descriptions.marker_sets)
        data_descriptions.num_rigid_bodies = len(data_descriptions.rigid_bodies)
        self.lc.publish('OPTITRACK_DATA_DESCRIPTIONS', data_descriptions.encode())

    def __processMessage( self, data ):
        trace( "Begin Packet\n------------\n" )

        messageID, = Int16Value.unpack(data[0:2])
        trace( "Message ID:", messageID )

        packetSize, = Int16Value.unpack(data[2:4])
        trace( "Packet Size:", packetSize )

        offset = 4
        if( messageID == self.NAT_FRAMEOFDATA ):
            self.__unpackMocapData( data[offset:] )
        elif( messageID == self.NAT_MODELDEF ):
            self.__unpackDataDescriptions( data[offset:] )
        elif( messageID == self.NAT_PINGRESPONSE ):
            offset += 256   # Skip the sending app's Name field
            offset += 4     # Skip the sending app's Version info
            self.__natNetStreamVersion = struct.unpack( 'BBBB', data[offset:offset+4] )
            offset += 4
        elif( messageID == self.NAT_RESPONSE ):
            if( packetSize == 4 ):
                commandResponse, = Int32Value.unpack(data[offset:offset + 4])
                offset += 4
            else:
                message, separator, remainder = bytes(data[offset:]).partition( b'\0' )
                offset += len( message ) + 1
                trace( "Command response:", message.decode( 'utf-8' ) )
        elif( messageID == self.NAT_UNRECOGNIZED_REQUEST ):
            trace( "Received 'Unrecognized request' from server" )
        elif( messageID == self.NAT_MESSAGESTRING ):
            message, separator, remainder = bytes(data[offset:]).partition( b'\0' )
            offset += len( message ) + 1
            trace( "Received message from server:", message.decode( 'utf-8' ) )
        else:
            trace( "ERROR: Unrecognized packet type" )

        trace( "End Packet\n----------\n" )

    def sendCommand( self, command, commandStr, socket, address ):
        # Compose the message in our known message format
        if( command == self.NAT_REQUEST_MODELDEF or command == self.NAT_REQUEST_FRAMEOFDATA ):
            packetSize = 0
            commandStr = ""
        elif( command == self.NAT_REQUEST ):
            packetSize = len( commandStr ) + 1
        elif( command == self.NAT_PING ):
            commandStr = "Ping"
            packetSize = len( commandStr ) + 1

        data = Int16Value.pack(command)
        data += Int16Value.pack(packetSize)

        data += commandStr.encode( 'utf-8' )
        data += b'\0'

        socket.sendto( data, address )

    def run( self ):
        # Create the data socket
        dataSocket = self.__createDataSocket( self.dataPort )
        if( dataSocket is None ):
            print( "Could not open data channel" )
            exit

        # Create the command socket
        commandSocket = self.__createCommandSocket()
        if( commandSocket is None ):
            print( "Could not open command channel" )
            exit

        server_poll_period = 1  # seconds
        last_server_poll = 0
        while True:
            # Block for input
            rlist, _wlist, _xlist = select.select(
                [dataSocket.fileno(), commandSocket.fileno()], [], [],
                server_poll_period)

            if commandSocket.fileno() in rlist:
                data, addr = commandSocket.recvfrom( 32768 ) # 32k byte buffer size
                if( len( data ) > 0 ):
                    self.__processMessage( data )

            if dataSocket.fileno() in rlist:
                data, addr = dataSocket.recvfrom( 32768 ) # 32k byte buffer size
                if( len( data ) > 0 ):
                    if self.serverIPAddress is None:
                        self.serverIPAddress = addr[0]
                    self.__processMessage( data )

            if (self.serverIPAddress is not None and
                time.time() > last_server_poll + server_poll_period):
                self.sendCommand( self.NAT_REQUEST_MODELDEF, "", commandSocket,
                                  (self.serverIPAddress, self.commandPort) )
                last_server_poll = time.time()


def main():
    parser = argparse.ArgumentParser(
        description='Translates NatNet data into LCM messages')
    parser.add_argument('--multicast-address', default='239.255.42.99',
                        help="The multicast address listed in Motive's " +
                        "streaming settings.")
    parser.add_argument('--local-address', default='',
                        help="IP address of the local interface to listen on")
    args = parser.parse_args()

    client = NatNetClient(args)
    client.run()

if __name__ == "__main__":
    main()
