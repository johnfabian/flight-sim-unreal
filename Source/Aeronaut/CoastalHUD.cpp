#include "FlightGame.h"
#include "CoastalScene.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
void AFlightHUD::DrawCoastalHUD(AFlightPawn* Pawn) {
    const auto& S=Pawn->Flight; const auto T=Pawn->GetTelemetry(); using FlightSim::Status;
    const float Scale=FMath::Min(Canvas->SizeX/1280.f,Canvas->SizeY/720.f);
    const float Ox=(Canvas->SizeX-1280*Scale)/2,Oy=(Canvas->SizeY-720*Scale)/2;
    const FLinearColor White(.88f,.91f,.85f),Muted(.61f,.68f,.63f),Warm(.88f,.62f,.30f),Panel(.018f,.025f,.023f,.76f);
    auto Box=[&](float X,float Y,float W,float H,FLinearColor C){DrawRect(C,Ox+X*Scale,Oy+Y*Scale,W*Scale,H*Scale);};
    auto Text=[&](const FString& V,float X,float Y,float Size,FLinearColor C){DrawText(V,C,Ox+X*Scale,Oy+Y*Scale,GEngine->GetMediumFont(),Size*Scale,false);};
    Box(28,26,262,68,Panel); Box(28,26,2,68,Warm);
    Text(TEXT("A E R O N A U T"),44,35,1.25f,White);
    const auto* Scene=Pawn->CoastalScene;
    Text(Scene->RegionLabel,45,66,.63f,Muted);
    const bool Tour=Pawn->Experience==EFlightExperience::GuidedTour;
    Text(Tour?TEXT("GUIDED FLYOVER"):TEXT("FREE FLIGHT"),1040,34,.85f,White);
    Text(Pawn->PerformancePreset?TEXT("PERFORMANCE  /  720P"):TEXT("QUALITY  /  720P"),1040,58,.60f,Muted);
    if(Pawn->CameraMode!=1) {
        Box(28,628,565,59,Panel);
        Text(FString::Printf(TEXT("%03.0f"),T.AirspeedKnots),44,640,1.65f,White); Text(TEXT("KTS"),103,656,.6f,Muted);
        Text(FString::Printf(TEXT("%04.0f"),T.AltitudeFeet),151,640,1.65f,White); Text(TEXT("FT MSL"),225,656,.6f,Muted);
        Text(FString::Printf(TEXT("%03.0f"),T.HeadingDegrees),303,640,1.65f,White); Text(TEXT("HDG"),365,656,.6f,Muted);
        Text(FString::Printf(TEXT("%02.0f"),T.PowerPercent),444,640,1.65f,White); Text(TEXT("% POWER"),491,656,.6f,Muted);
    } else {
        // The analogue hand shows hundreds; retain an absolute altitude readout.
        Box(28,647,236,40,Panel);
        Text(FString::Printf(TEXT("%04.0f FT MSL   /   %03.0f KTS"),T.AltitudeFeet,T.AirspeedKnots),42,660,.85f,White);
    }
    Text(TEXT("C / Y  CAMERA    T / VIEW  TOUR    P / MENU  PAUSE"),797,665,.63f,White);
    Text(TEXT("F2  HIDE HUD    H  CONTROLS    F3  PERFORMANCE"),30,699,.55f,Muted);
    if(Pawn->ShowPerformance) Text(FString::Printf(TEXT("%.0f FPS  /  %.1f ms  /  DX11"),1000.f/FMath::Max(Pawn->SmoothedFrameMs,.01f),Pawn->SmoothedFrameMs),990,699,.65f,Warm);
    if(Tour) {
        Box(1040,83,209,2,Panel); Box(1040,83,209*Pawn->TourTime/FMath::Max(Scene->TourDuration,1.f),2,Warm);
    }
    if(Pawn->ShowHelp) {
        Box(28,512,590,98,Panel);
        Text(TEXT("S/W pitch   A/D bank   Q/E rudder   Shift/Ctrl power"),44,526,.75f,White);
        Text(TEXT("Controller: left stick fly   LB/RB rudder   RT/LT power"),44,553,.72f,White);
        Text(TEXT("Enter/A start   R reset   T/View guided tour   Alt+F4 quit"),44,580,.68f,Muted);
    }
    if(!Scene->AttributionLine1.IsEmpty() && (Pawn->ShowHelp || S.status!=Status::Flying)) {
        Box(650,538,600,64,Panel);
        Text(Scene->AttributionLine1,665,548,.72f,White);
        Text(Scene->AttributionLine2,665,577,.68f,Muted);
    }
    if(S.stall) Text(TEXT("LOW AIRSPEED - INCREASE POWER"),455,565,.95f,Warm);
    if(S.status!=Status::Flying) {
        Box(28,248,473,243,Panel); Box(28,248,473,2,Warm);
        FString Title=Scene->BriefingTitle; FString Sub=Scene->BriefingSubtitle;
        if(S.status==Status::Paused) {Title=TEXT("Flight paused.");Sub=TEXT("Resume your flight, or take the guided tour.");}
        if(S.status==Status::Crashed) {Title=TEXT("Flight ended.");Sub=TEXT("Clear the terrain, buildings and water on your next flight.");}
        Text(Scene->BriefingLabel,51,273,.63f,Warm);
        Text(Title,50,306,1.7f,White); Text(Sub,51,353,.72f,Muted);
        Text(Scene->StartLabel,51,401,.95f,White);
        Text(FString::Printf(TEXT("T / VIEW     GUIDED FLYOVER - %.0f SECONDS"),Scene->TourDuration),51,436,.83f,Warm);
        Text(TEXT("STARTS AIRBORNE  /  ASSISTED FLIGHT"),51,470,.59f,Muted);
    }
}
