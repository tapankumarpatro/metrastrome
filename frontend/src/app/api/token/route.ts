import { AccessToken } from "livekit-server-sdk";
import { NextRequest, NextResponse } from "next/server";

const LIVEKIT_API_KEY = process.env.LIVEKIT_API_KEY || "devkey";
const LIVEKIT_API_SECRET = process.env.LIVEKIT_API_SECRET || "devsecret";

export async function POST(req: NextRequest) {
  try {
    const { identity, roomName } = await req.json();

    if (!identity || !roomName) {
      return NextResponse.json(
        { error: "identity and roomName are required" },
        { status: 400 }
      );
    }

    const token = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
      identity,
      ttl: "1h",
    });

    token.addGrant({
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
    });

    const jwt = await token.toJwt();

    return NextResponse.json({ token: jwt });
  } catch (error) {
    console.error("Token generation error:", error);
    return NextResponse.json(
      { error: "Failed to generate token" },
      { status: 500 }
    );
  }
}
