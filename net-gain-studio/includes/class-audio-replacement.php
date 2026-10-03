<?php
/**
 * Audio replacement for an already-recorded episode (Spec Section 8.4).
 *
 * Available to an administrator and to the show's designated host, at any
 * point after the first audio upload. This class owns the synchronous half:
 * swapping the master attachment, updating the page's structured-data audio
 * URL, restarting a running finalization countdown, and writing a replacement
 * record. (The website's player is Captivate's embed, so listeners on the
 * site hear the new audio when Captivate's copy is swapped, not before.) The
 * asynchronous half (Captivate media swap; deleting and re-creating the
 * YouTube video) is carried out by the Python tick loop from that record -
 * the same one-execution-path rule as every other manual trigger (CLAUDE.md).
 *
 * Graphics and metadata are never touched: they are assumed fine.
 *
 * The record lives in ng_audio_replacement:
 *   id, status (pending|done|failed), requested_at (GMT), requested_by,
 *   previous_attachment_id, new_attachment_id, completed_at,
 *   destinations: { captivate|youtube: { status (pending|done|failed|skipped),
 *   note, at, + destination-specific facts such as the uploaded media_id } }
 * ng_audio_replacement_pending is a cheap 1/absent flag mirroring
 * status === 'pending', so the tick-context query never scans every episode.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Audio_Replacement {

	const META         = 'ng_audio_replacement';
	const PENDING_FLAG = 'ng_audio_replacement_pending';
	const LOG          = 'ng_audio_replacement_log';

	const DESTINATIONS = array( 'captivate', 'youtube' );
	const DEST_STATUS  = array( 'pending', 'done', 'failed', 'skipped' );

	public static function get_record( $episode_id ) {
		$record = get_post_meta( $episode_id, self::META, true );
		return is_array( $record ) ? $record : null;
	}

	/**
	 * Swaps the episode's audio and queues the downstream work. Returns the
	 * new record, or a WP_Error. Permission is the caller's job (REST route).
	 */
	public static function request( $episode_id, $attachment_id, $user_id ) {
		$episode_id    = (int) $episode_id;
		$attachment_id = (int) $attachment_id;

		if ( ! wp_attachment_is( 'audio', $attachment_id ) ) {
			return new WP_Error( 'ng_invalid_attachment', 'That attachment is not an audio file.', array( 'status' => 400 ) );
		}
		// A host can only use a file they uploaded themselves, not any audio file
		// that happens to be in the shared media library. (Not edit_post on the
		// attachment: the talent role has only read + upload_files, so WordPress
		// would refuse that even for their own upload.) Administrators may use any.
		$attachment = get_post( $attachment_id );
		$is_owner   = $attachment && (int) $attachment->post_author === (int) $user_id;
		if ( ! $is_owner && ! Net_Gain_REST_Permissions::can_manage_episode( $episode_id ) ) {
			return new WP_Error( 'ng_attachment_forbidden', 'You can only use an audio file you uploaded yourself.', array( 'status' => 403 ) );
		}

		$current_id  = (int) get_post_meta( $episode_id, 'ng_audio_attachment_id', true );
		$step_status = get_post_meta( $episode_id, 'ng_step_status', true );
		$step_status = is_array( $step_status ) ? $step_status : Net_Gain_Step_Status::default_status();
		$audio_state = $step_status['audio_received']['status'] ?? 'pending';

		if ( ! $current_id || ! in_array( $audio_state, array( 'done', 'degraded' ), true ) ) {
			return new WP_Error(
				'ng_no_audio_to_replace',
				'This episode has no audio yet - use Upload Audio instead.',
				array( 'status' => 409 )
			);
		}
		if ( $attachment_id === $current_id ) {
			return new WP_Error( 'ng_same_audio', 'That is already this episode\'s audio file.', array( 'status' => 400 ) );
		}

		$existing = self::get_record( $episode_id );
		if ( $existing && 'pending' === ( $existing['status'] ?? '' ) ) {
			return new WP_Error(
				'ng_replacement_in_progress',
				'An audio replacement for this episode is still being carried out - wait for it to finish before replacing the audio again.',
				array( 'status' => 409 )
			);
		}

		update_post_meta( $episode_id, 'ng_audio_attachment_id', $attachment_id );

		// A countdown still running gets a fresh window, exactly as a normal
		// replacement upload does (class-rest-episode-steps.php). A finalized
		// episode stays finalized: its queued publish simply uses the new file.
		$finalization = get_post_meta( $episode_id, 'ng_finalization', true );
		if ( is_array( $finalization ) && 'counting_down' === ( $finalization['state'] ?? '' ) ) {
			$finalization['countdown_started_at'] = current_time( 'mysql', true );
			update_post_meta( $episode_id, 'ng_finalization', $finalization );
		}

		// audio_file on the public post is a copy made at publish time that feeds
		// only the page's schema.org contentUrl (the visible player is Captivate's
		// embed) - keep it pointing at the current master.
		$website_post_id = (int) get_post_meta( $episode_id, 'ng_website_post_id', true );
		if ( $website_post_id ) {
			update_post_meta( $website_post_id, 'audio_file', wp_get_attachment_url( $attachment_id ) );
		}

		$destinations = array();
		foreach ( self::DESTINATIONS as $destination ) {
			$destinations[ $destination ] = array( 'status' => 'pending', 'note' => '', 'at' => null );
		}
		$record = array(
			'id'                     => wp_generate_uuid4(),
			'status'                 => 'pending',
			'requested_at'           => current_time( 'mysql', true ),
			'requested_by'           => (int) $user_id,
			'previous_attachment_id' => $current_id,
			'new_attachment_id'      => $attachment_id,
			'completed_at'           => null,
			'destinations'           => $destinations,
		);
		update_post_meta( $episode_id, self::META, $record );
		update_post_meta( $episode_id, self::PENDING_FLAG, 1 );

		$log   = get_post_meta( $episode_id, self::LOG, true );
		$log   = is_array( $log ) ? $log : array();
		$log[] = array(
			'id'   => $record['id'],
			'at'   => $record['requested_at'],
			'by'   => (int) $user_id,
			'from' => $current_id,
			'to'   => $attachment_id,
		);
		update_post_meta( $episode_id, self::LOG, $log );

		return $record;
	}

	/**
	 * Called by the tick loop (via REST) as each destination finishes. Merges
	 * $data into that destination's record without otherwise changing it, then
	 * recomputes the overall status.
	 */
	public static function update_destination( $episode_id, $destination, $status, $note, array $data ) {
		if ( ! in_array( $destination, self::DESTINATIONS, true ) ) {
			return new WP_Error( 'ng_invalid_destination', 'Unknown destination: ' . $destination, array( 'status' => 400 ) );
		}
		if ( ! in_array( $status, self::DEST_STATUS, true ) ) {
			return new WP_Error( 'ng_invalid_status', 'Unknown status: ' . $status, array( 'status' => 400 ) );
		}
		$record = self::get_record( $episode_id );
		if ( ! $record ) {
			return new WP_Error( 'ng_no_replacement', 'This episode has no audio replacement on record.', array( 'status' => 404 ) );
		}

		$entry                              = isset( $record['destinations'][ $destination ] ) ? $record['destinations'][ $destination ] : array();
		$entry                              = array_merge( $entry, $data );
		$entry['status']                    = $status;
		$entry['note']                      = $note;
		$entry['at']                        = current_time( 'mysql', true );
		$record['destinations'][ $destination ] = $entry;

		$record = self::with_overall_status( $record );
		update_post_meta( $episode_id, self::META, $record );
		if ( 'pending' === $record['status'] ) {
			update_post_meta( $episode_id, self::PENDING_FLAG, 1 );
		} else {
			delete_post_meta( $episode_id, self::PENDING_FLAG );
		}
		return $record;
	}

	/** Puts every failed destination back to pending (keeps what they already recorded, e.g. an uploaded media_id). */
	public static function retry( $episode_id ) {
		$record = self::get_record( $episode_id );
		if ( ! $record || 'failed' !== ( $record['status'] ?? '' ) ) {
			return new WP_Error( 'ng_nothing_to_retry', 'There is no failed audio replacement to retry on this episode.', array( 'status' => 409 ) );
		}
		foreach ( $record['destinations'] as $destination => $entry ) {
			if ( 'failed' === ( $entry['status'] ?? '' ) ) {
				$record['destinations'][ $destination ]['status'] = 'pending';
				$record['destinations'][ $destination ]['note']   = '';
			}
		}
		$record['status']       = 'pending';
		$record['completed_at'] = null;
		update_post_meta( $episode_id, self::META, $record );
		update_post_meta( $episode_id, self::PENDING_FLAG, 1 );
		return $record;
	}

	private static function with_overall_status( array $record ) {
		$any_pending = false;
		$any_failed  = false;
		foreach ( $record['destinations'] as $entry ) {
			$status = $entry['status'] ?? 'pending';
			if ( 'pending' === $status ) {
				$any_pending = true;
			} elseif ( 'failed' === $status ) {
				$any_failed = true;
			}
		}
		if ( $any_pending ) {
			$record['status']       = 'pending';
			$record['completed_at'] = null;
		} else {
			$record['status']       = $any_failed ? 'failed' : 'done';
			$record['completed_at'] = current_time( 'mysql', true );
		}
		return $record;
	}

	/** For the tick context: every episode of this show with a replacement still to be carried out. */
	public static function pending_for_show( $show_id ) {
		$episodes = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Episode::POST_TYPE,
				'post_status'    => 'publish',
				'post_parent'    => $show_id,
				'posts_per_page' => 50,
				'fields'         => 'ids',
				'meta_key'       => self::PENDING_FLAG,
				'meta_value'     => 1,
			)
		);
		$result = array();
		foreach ( $episodes as $episode_id ) {
			$record = self::get_record( $episode_id );
			if ( ! $record || 'pending' !== ( $record['status'] ?? '' ) ) {
				continue;
			}
			$result[] = array(
				'episode_id'             => (int) $episode_id,
				'id'                     => $record['id'],
				'new_attachment_id'      => (int) $record['new_attachment_id'],
				'previous_attachment_id' => (int) $record['previous_attachment_id'],
				'destinations'           => $record['destinations'],
			);
		}
		return $result;
	}

	// --- UI -------------------------------------------------------------------

	/** Plain-language account of what replacing the audio will do to THIS episode right now. */
	public static function confirm_message( $episode_id ) {
		$lines   = array( 'Replace this episode\'s audio file?' );
		$effects = array();

		if ( get_post_meta( $episode_id, 'ng_url_captivate', true ) ) {
			$effects[] = '• Captivate: the audio is swapped. Nothing else about the episode there changes. The player on the website is Captivate\'s, so it follows.';
		}
		if ( get_post_meta( $episode_id, 'ng_youtube_video_id', true ) ) {
			$effects[] = '• YouTube: the current video is DELETED and a new one is created from the new audio. It will be a different video at a different URL.';
		}
		$finalization = get_post_meta( $episode_id, 'ng_finalization', true );
		if ( is_array( $finalization ) && 'counting_down' === ( $finalization['state'] ?? '' ) ) {
			$effects[] = '• The finalization countdown restarts.';
		}

		if ( $effects ) {
			$lines[] = '';
			$lines   = array_merge( $lines, $effects );
		} else {
			$lines[] = '';
			$lines[] = 'It has not been published to Captivate or YouTube yet, so the new file will simply be used when it publishes.';
		}
		$lines[] = '';
		$lines[] = 'Images and metadata are not regenerated.';
		return implode( "\n", $lines );
	}

	/**
	 * The "Replace audio" control plus any in-flight/last-result status. Quiet
	 * on purpose: a secondary small button beside the audio, a one-line status
	 * only when there is something to report.
	 */
	public static function render_control( $episode_id ) {
		$record  = self::get_record( $episode_id );
		$pending = $record && 'pending' === ( $record['status'] ?? '' );
		?>
		<span class="ng-audio-replace">
			<?php if ( $pending ) : ?>
				<button type="button" class="button button-small" disabled>Replacing audio…</button>
			<?php else : ?>
				<button type="button" class="button button-small ng-replace-audio"
					data-episode-id="<?php echo esc_attr( $episode_id ); ?>"
					data-confirm="<?php echo esc_attr( self::confirm_message( $episode_id ) ); ?>">Replace audio…</button>
			<?php endif; ?>
		</span>
		<?php
		self::render_status( $episode_id );
	}

	public static function render_status( $episode_id ) {
		$record = self::get_record( $episode_id );
		if ( ! $record ) {
			return;
		}
		$status = $record['status'] ?? '';
		$labels = array(
			'captivate' => 'Captivate',
			'youtube'   => 'YouTube',
		);
		$bits = array();
		foreach ( $record['destinations'] as $destination => $entry ) {
			$dest_status = $entry['status'] ?? 'pending';
			if ( 'skipped' === $dest_status ) {
				continue; // nothing to do there - not worth mentioning.
			}
			$word   = array(
				'pending' => 'in progress',
				'done'    => 'done',
				'failed'  => 'FAILED',
			);
			$bits[] = ( $labels[ $destination ] ?? $destination ) . ': ' . ( $word[ $dest_status ] ?? $dest_status );
		}

		if ( 'pending' === $status ) {
			$message = 'Audio replacement under way' . ( $bits ? ' — ' . implode( ', ', $bits ) : '' ) . '. This finishes on the next few passes of the background job.';
			$color   = '';
		} elseif ( 'failed' === $status ) {
			$failures = array();
			foreach ( $record['destinations'] as $destination => $entry ) {
				if ( 'failed' === ( $entry['status'] ?? '' ) ) {
					$failures[] = ( $labels[ $destination ] ?? $destination ) . ': ' . ( $entry['note'] ?? '' );
				}
			}
			$message = 'Audio replacement failed — ' . implode( ' | ', $failures );
			$color   = 'color:#a00;';
		} else {
			$message = 'Audio replaced' . ( $bits ? ' — ' . implode( ', ', $bits ) : '' ) . '.';
			$color   = '';
		}
		?>
		<p class="description" style="margin:6px 0 0;<?php echo esc_attr( $color ); ?>">
			<?php echo esc_html( $message ); ?>
			<?php if ( 'failed' === $status ) : ?>
				<button type="button" class="button button-small ng-retry-audio-replacement" data-episode-id="<?php echo esc_attr( $episode_id ); ?>">Retry</button>
			<?php endif; ?>
		</p>
		<?php
	}
}
