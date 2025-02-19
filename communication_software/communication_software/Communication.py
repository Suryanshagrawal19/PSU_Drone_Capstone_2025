import asyncio
from websockets.legacy.server import WebSocketServerProtocol
import websockets
from pymavlink import mavutil
from communication_software.CoordinateHandler import Coordinate
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")


class Communication():
    """
    Class that handles both WebSocket and MAVLink communication.
    It starts a WebSocket server to communicate with a client and also listens
    for MAVLink messages (e.g., from a SITL simulator) to update coordinates.
    """
    
    def __init__(self, mav_ip: str = '127.0.0.1', mav_port: int = 1455) -> None:
        # Initial coordinates and angle
        self.lat = "0"
        self.lng = "0"
        self.alt = "0"
        self.angle = "0"
        self.connections = set()
        
        # Set up a MAVLink connection (UDP connection string)
        self.mav_connection = mavutil.mavlink_connection(f'udp:{mav_ip}:{mav_port}')

    async def send_coordinates_websocket(self, coordinates: Coordinate, angle: int, ip: str) -> None:
        # Your implementation here
        # For example:
        self.lat = str(coordinates.lat)[0:9]
        self.lng = str(coordinates.lng)[0:9]
        self.alt = str(coordinates.alt)[0:2]
        self.angle = str(angle)

        server = await websockets.serve(self.webs_server, ip, 14500)
        print("WebSocket server started.")
        await server.wait_closed()

    async def webs_server(self, ws: websockets.WebSocketServerProtocol, path: str) -> None:
        """
        Method called when a WebSocket client connects.
        """
        print("Client connected from:", ws.remote_address[0])
        self.connections.add(ws)
        
        try:
            # Continuously wait for messages from the client.
            async for data in ws:
                await self.on_message(data)
        except websockets.exceptions.ConnectionClosedError:
            print("Client disconnected.")
        finally:
            self.connections.remove(ws)

    async def on_message(self, frame: websockets.Data) -> None:
        """
        Process incoming WebSocket messages.
        If the client requests coordinates, send them.
        """
        print(f"Received: {frame}")
        if frame == "REQ/COORDS":
            await self.send_coords()
        else:
            print("Received frame with size:", len(frame))
            print(frame)

    async def send_coords(self) -> None:
        """
        Send the current coordinates to all connected WebSocket clients.
        """
        message = f"COORDS/{self.lat}/{self.lng}/{self.alt}/{self.angle}"
        for connection in self.connections:
            await connection.send(message)
        print(f"Sent: {message}")

    async def listen_mavlink(self):
        """
        Listen for MAVLink messages. When a new GLOBAL_POSITION_INT message is received,
        update the coordinate values and send them over WebSocket.
        """
        # Wait for a heartbeat to confirm the MAVLink connection is active.
        self.mav_connection.wait_heartbeat()
        print("MAVLink heartbeat received. Listening for MAVLink messages...")
        while True:
            # This call is blocking until a message is received.
            msg = self.mav_connection.recv_match(blocking=True)
            if msg:
                print("Received MAVLink message:", msg)
                if msg.get_type() == "GLOBAL_POSITION_INT":
                    # Update coordinates from the message.
                    # lat and lon are in degrees * 1e7, alt is in millimeters.
                    self.lat = str(msg.lat / 1e7)[0:9]
                    self.lng = str(msg.lon / 1e7)[0:9]
                    # Convert altitude to meters and take the first two characters.
                    self.alt = str(msg.alt / 1000)[0:2]
                    # Heading (hdg) is provided in 1/100 degrees.
                    self.angle = str(msg.hdg / 100 if msg.hdg is not None else 0)
                    print(f"Updated coordinates: lat={self.lat}, lng={self.lng}, alt={self.alt}, angle={self.angle}")
                    
                    # Optionally, immediately push new coordinates to all WebSocket clients.
                    await self.send_coords()
            # Yield control briefly to keep the loop responsive.
            await asyncio.sleep(0.1)

    async def run(self, coordinates: Coordinate, angle: int, ip: str):
        """
        Run both the WebSocket server and the MAVLink listener concurrently.
        """
        websocket_task = asyncio.create_task(self.start_websocket_server(ip))
        mavlink_task = asyncio.create_task(self.listen_mavlink())

        await asyncio.gather(websocket_task, mavlink_task)

    async def start_websocket_server(self, ip: str) -> None:
        """
        Start WebSocket server and keep it running.
        """
        server = await websockets.serve(self.webs_server, ip, 14500)
        print(f"WebSocket server started at ws://{ip}:14500")
        await server.wait_closed()

    async def start_video_stream(self):
        # Send MAVLink command to start video streaming
        self.mav_connection.mav.command_long_send(
            self.mav_connection.target_system, 
            self.mav_connection.target_component,
            mavutil.mavlink.MAV_CMD_VIDEO_STREAM_START,
            0,  # Confirmation (usually 0)
            0, 0, 0, 0, 0, 0, 0
        )
        print("Started video stream")

    # WebSocket video stream handler (pseudocode)
    async def send_video_frame(self, frame_data):
        # Send video frames as WebSocket messages
        for connection in self.connections:
            await connection.send(frame_data)
            print(f"Sent video frame to {connection.remote_address[0]}")
        

# Example usage:
if __name__ == "__main__":
    # Example coordinate (you may replace with actual values or a dynamic source)
    coordinate = Coordinate(lat=37.7749, lng=-122.4194, alt=100)
    initial_angle = 45
    websocket_ip = "localhost"  # Use appropriate IP

    comm = Communication()  # Uses default MAVLink connection to udp:127.0.0.1:14550
    asyncio.run(comm.run(coordinate, initial_angle, websocket_ip))
