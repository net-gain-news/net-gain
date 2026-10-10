<?php
/**
 * REST routes for the per-show photo library (see class-photo-library.php).
 *
 * Used by two clients: the admin "Photos" screen (cookie auth + X-WP-Nonce, or ?_wpnonce= for <img> previews) and the
 * pipeline's service account (application password) - it lists eligible photos, fetches an original to render from,
 * writes the tags its vision step produced, and records which episode used which photo.
 *
 * Every route is gated on managing the photo's SHOW (the same capability the other show routes use). Originals and
 * previews are streamed from a private directory; they are never reachable by URL.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_REST_Photos {

	const NS = 'net-gain/v1';

	public function register_routes() {
		$manage_show = function ( WP_REST_Request $request ) {
			return Net_Gain_REST_Permissions::can_manage_show( (int) $request['id'] );
		};
		$manage_photo = function ( WP_REST_Request $request ) {
			$post = get_post( (int) $request['id'] );
			return $post && Net_Gain_Photo_Library::POST_TYPE === $post->post_type
				&& Net_Gain_REST_Permissions::can_manage_show( (int) $post->post_parent );
		};

		register_rest_route( self::NS, '/shows/(?P<id>\d+)/photos', array(
			array( 'methods' => 'GET', 'callback' => array( $this, 'list_photos' ), 'permission_callback' => $manage_show ),
			array( 'methods' => 'POST', 'callback' => array( $this, 'upload' ), 'permission_callback' => $manage_show ),
		) );
		register_rest_route( self::NS, '/shows/(?P<id>\d+)/photo-stats', array(
			'methods' => 'GET', 'callback' => array( $this, 'stats' ), 'permission_callback' => $manage_show,
		) );
		register_rest_route( self::NS, '/photos/(?P<id>\d+)/thumb', array(
			'methods' => 'GET', 'callback' => array( $this, 'thumb' ), 'permission_callback' => $manage_photo,
		) );
		register_rest_route( self::NS, '/photos/(?P<id>\d+)/file', array(
			'methods' => 'GET', 'callback' => array( $this, 'file' ), 'permission_callback' => $manage_photo,
		) );
		register_rest_route( self::NS, '/photos/(?P<id>\d+)', array(
			array( 'methods' => 'POST', 'callback' => array( $this, 'update' ), 'permission_callback' => $manage_photo ),
			array( 'methods' => 'DELETE', 'callback' => array( $this, 'delete' ), 'permission_callback' => $manage_photo ),
		) );
		register_rest_route( self::NS, '/photos/(?P<id>\d+)/used', array(
			'methods' => 'POST', 'callback' => array( $this, 'used' ), 'permission_callback' => $manage_photo,
		) );
	}

	// --- reading ----------------------------------------------------------------------------------

	public function list_photos( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$cooldown = Net_Gain_Photo_Library::cooldown_days( $show_id );
		$for_date = $this->date_param( $request->get_param( 'for_date' ) );
		list( $dir, $outside ) = Net_Gain_Photo_Library::private_dir();

		return rest_ensure_response(
			array(
				'cooldown_days' => $cooldown,
				'for_date'      => $for_date,
				'storage'       => array( 'ok' => (bool) $dir, 'outside_webroot' => $outside ),
				'photos'        => Net_Gain_Photo_Library::list_for_show( $show_id, $cooldown, $for_date ),
			)
		);
	}

	public function stats( WP_REST_Request $request ) {
		$show_id  = (int) $request['id'];
		$cooldown = Net_Gain_Photo_Library::cooldown_days( $show_id );
		$for_date = $this->date_param( $request->get_param( 'for_date' ) );
		$photos   = Net_Gain_Photo_Library::list_for_show( $show_id, $cooldown, $for_date );
		return rest_ensure_response(
			Net_Gain_Photo_Library::stats( $photos, $cooldown, $for_date, Net_Gain_Photo_Library::episodes_per_week( $show_id ) )
		);
	}

	public function thumb( WP_REST_Request $request ) {
		$id   = (int) $request['id'];
		$path = Net_Gain_Photo_Library::file_path( get_post_meta( $id, 'ng_photo_thumb', true ) );
		if ( ! $path || ! is_readable( $path ) ) {
			$path = Net_Gain_Photo_Library::file_path( get_post_meta( $id, 'ng_photo_file', true ) ); // no preview was made
		}
		return $this->stream( $path, 3600 );
	}

	public function file( WP_REST_Request $request ) {
		$path = Net_Gain_Photo_Library::file_path( get_post_meta( (int) $request['id'], 'ng_photo_file', true ) );
		return $this->stream( $path, 0 );
	}

	private function stream( $path, $max_age ) {
		if ( ! $path || ! is_readable( $path ) ) {
			return new WP_Error( 'ng_photo_file_missing', 'The photo file is not available.', array( 'status' => 404 ) );
		}
		$info = @getimagesize( $path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
		$mime = $info && ! empty( $info['mime'] ) ? $info['mime'] : 'application/octet-stream';
		while ( ob_get_level() ) {
			ob_end_clean();
		}
		header( 'Content-Type: ' . $mime );
		header( 'Content-Length: ' . filesize( $path ) );
		header( 'Cache-Control: ' . ( $max_age ? 'private, max-age=' . (int) $max_age : 'private, no-store' ) );
		header( 'X-Robots-Tag: noindex, noarchive' );
		readfile( $path ); // phpcs:ignore WordPress.WP.AlternativeFunctions.file_system_operations_readfile
		exit;
	}

	// --- upload -----------------------------------------------------------------------------------

	public function upload( WP_REST_Request $request ) {
		$show_id = (int) $request['id'];
		$show    = get_post( $show_id );
		if ( ! $show || Net_Gain_CPT_Show::POST_TYPE !== $show->post_type ) {
			return new WP_Error( 'ng_show_not_found', 'Show not found.', array( 'status' => 404 ) );
		}

		$files = $request->get_file_params();
		$file  = $files['file'] ?? null;
		if ( ! $file || ! empty( $file['error'] ) || empty( $file['tmp_name'] ) ) {
			return new WP_Error( 'ng_upload_failed', 'The file did not upload (it may be larger than the server allows).', array( 'status' => 400 ) );
		}

		$name = sanitize_file_name( $file['name'] ?? 'photo' );
		if ( filesize( $file['tmp_name'] ) > Net_Gain_Photo_Library::MAX_BYTES ) {
			return new WP_Error( 'ng_upload_too_big', $name . ' is larger than 50 MB.', array( 'status' => 400 ) );
		}

		$info = @getimagesize( $file['tmp_name'] ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged
		$ext  = '';
		if ( $info ) {
			$ext = array( IMAGETYPE_JPEG => 'jpg', IMAGETYPE_PNG => 'png', IMAGETYPE_WEBP => 'webp' )[ $info[2] ] ?? '';
		}
		if ( ! $info || ! $ext ) {
			return new WP_Error( 'ng_upload_not_photo', $name . ' is not a JPEG, PNG or WebP photo. (Photos only.)', array( 'status' => 400 ) );
		}

		$problem = Net_Gain_Photo_Library::check_dimensions( (int) $info[0], (int) $info[1] );
		if ( $problem ) {
			return new WP_Error( 'ng_upload_too_small', $name . ': ' . $problem, array( 'status' => 400 ) );
		}

		// Real photographs only: reject a file whose own metadata declares AI generation or AI editing.
		$handle = fopen( $file['tmp_name'], 'rb' );
		$bytes  = '';
		if ( $handle ) {
			$bytes = (string) fread( $handle, 262144 );
			$size  = filesize( $file['tmp_name'] );
			if ( $size > 262144 ) {
				fseek( $handle, max( 262144, $size - 262144 ) );
				$bytes .= (string) fread( $handle, 262144 );
			}
			fclose( $handle );
		}
		$markers = Net_Gain_Photo_Library::scan_provenance( $bytes );
		if ( $markers ) {
			return new WP_Error(
				'ng_upload_ai_origin',
				$name . ' was not added: its embedded metadata says it was AI-generated or AI-edited (' . implode( ', ', $markers ) . '). Only real photographs go in this library.',
				array( 'status' => 422 )
			);
		}

		$hash = hash_file( 'sha256', $file['tmp_name'] );
		$dupe = get_posts( array(
			'post_type' => Net_Gain_Photo_Library::POST_TYPE, 'post_status' => 'any', 'post_parent' => $show_id,
			'posts_per_page' => 1, 'fields' => 'ids', 'meta_key' => 'ng_photo_hash', 'meta_value' => $hash, // phpcs:ignore WordPress.DB.SlowDBQuery
		) );
		if ( $dupe ) {
			return new WP_Error( 'ng_upload_duplicate', $name . ' is already in the library.', array( 'status' => 409 ) );
		}

		list( $dir ) = Net_Gain_Photo_Library::private_dir();
		if ( ! $dir ) {
			return new WP_Error( 'ng_storage_unavailable', 'No writable private folder is available for photo storage. Ask your host for write access outside the web root.', array( 'status' => 500 ) );
		}

		$post_id = wp_insert_post( array(
			'post_type'   => Net_Gain_Photo_Library::POST_TYPE,
			'post_status' => 'publish',
			'post_parent' => $show_id,
			'post_title'  => $name,
		), true );
		if ( is_wp_error( $post_id ) ) {
			return $post_id;
		}

		$relative = $show_id . '/' . $post_id . '.' . $ext;
		$thumb    = $show_id . '/' . $post_id . '-preview.jpg';
		wp_mkdir_p( $dir . '/' . $show_id );
		$stored = @move_uploaded_file( $file['tmp_name'], $dir . '/' . $relative ) || @copy( $file['tmp_name'], $dir . '/' . $relative ); // phpcs:ignore
		if ( ! $stored ) {
			wp_delete_post( $post_id, true );
			return new WP_Error( 'ng_storage_write_failed', 'Could not save ' . $name . '.', array( 'status' => 500 ) );
		}

		$thumb_ok = false;
		$editor   = wp_get_image_editor( $dir . '/' . $relative );
		if ( ! is_wp_error( $editor ) ) {
			if ( method_exists( $editor, 'maybe_exif_rotate' ) ) {
				$editor->maybe_exif_rotate();
			}
			$editor->resize( 900, 900, false );
			$editor->set_quality( 82 );
			$saved    = $editor->save( $dir . '/' . $thumb, 'image/jpeg' );
			$thumb_ok = ! is_wp_error( $saved );
		}

		$flags = array();
		if ( Net_Gain_Photo_Library::is_low_res( (int) $info[0], (int) $info[1] ) ) {
			$flags[] = 'low_res';
		}

		$meta = array(
			'ng_photo_file'          => $relative,
			'ng_photo_thumb'         => $thumb_ok ? $thumb : '',
			'ng_photo_hash'          => $hash,
			'ng_photo_width'         => (int) $info[0],
			'ng_photo_height'        => (int) $info[1],
			'ng_photo_original_name' => $name,
			'ng_photo_status'        => Net_Gain_Photo_Library::STATUS_PENDING,
			'ng_photo_flags'         => $flags,
		);
		foreach ( $meta as $key => $value ) {
			update_post_meta( $post_id, $key, $value );
		}

		return rest_ensure_response( Net_Gain_Photo_Library::to_array( get_post( $post_id ) ) );
	}

	// --- changing ---------------------------------------------------------------------------------

	public function update( WP_REST_Request $request ) {
		$id   = (int) $request['id'];
		$body = $request->get_json_params();
		$body = is_array( $body ) ? $body : $request->get_params();

		if ( isset( $body['tags'] ) ) {
			$tags = array();
			foreach ( (array) $body['tags'] as $tag ) {
				$tag = trim( preg_replace( '/[^a-z0-9 _-]/', '', strtolower( (string) $tag ) ) );
				if ( '' !== $tag && strlen( $tag ) <= 32 ) {
					$tags[ $tag ] = $tag;
				}
			}
			update_post_meta( $id, 'ng_photo_tags', array_slice( array_values( $tags ), 0, 16 ) );
		}
		if ( isset( $body['topics'] ) ) {
			update_post_meta( $id, 'ng_photo_topics', array_values( array_intersect( Net_Gain_Photo_Library::TOPICS, (array) $body['topics'] ) ) );
		}
		if ( isset( $body['people'] ) && in_array( $body['people'], Net_Gain_Photo_Library::PEOPLE, true ) ) {
			update_post_meta( $id, 'ng_photo_people', $body['people'] );
		}
		foreach ( array( 'focal_x', 'focal_y' ) as $axis ) {
			if ( isset( $body[ $axis ] ) && is_numeric( $body[ $axis ] ) ) {
				update_post_meta( $id, 'ng_photo_' . $axis, max( 0.0, min( 1.0, (float) $body[ $axis ] ) ) );
			}
		}
		if ( isset( $body['description'] ) ) {
			update_post_meta( $id, 'ng_photo_description', mb_substr( sanitize_text_field( (string) $body['description'] ), 0, 300 ) );
		}
		if ( isset( $body['flags'] ) ) {
			$known = array( 'low_res', 'logo_text', 'needs_review', 'portrait' );
			update_post_meta( $id, 'ng_photo_flags', array_values( array_intersect( $known, (array) $body['flags'] ) ) );
		}
		foreach ( array( 'width', 'height' ) as $dim ) {
			if ( isset( $body[ $dim ] ) && (int) $body[ $dim ] > 0 ) {
				update_post_meta( $id, 'ng_photo_' . $dim, (int) $body[ $dim ] );
			}
		}
		if ( isset( $body['status'] ) && in_array( $body['status'], array( 'ready', 'retired', 'pending_tags' ), true ) ) {
			update_post_meta( $id, 'ng_photo_status', $body['status'] );
		}

		return rest_ensure_response( Net_Gain_Photo_Library::to_array( get_post( $id ) ) );
	}

	public function delete( WP_REST_Request $request ) {
		$id = (int) $request['id'];
		foreach ( array( 'ng_photo_file', 'ng_photo_thumb' ) as $key ) {
			$path = Net_Gain_Photo_Library::file_path( get_post_meta( $id, $key, true ) );
			if ( $path && is_file( $path ) ) {
				@unlink( $path ); // phpcs:ignore WordPress.PHP.NoSilencedErrors.Discouraged, WordPress.WP.AlternativeFunctions.unlink_unlink
			}
		}
		wp_delete_post( $id, true );
		return rest_ensure_response( array( 'deleted' => true, 'id' => $id ) );
	}

	public function used( WP_REST_Request $request ) {
		$id         = (int) $request['id'];
		$episode_id = (int) $request->get_param( 'episode_id' );
		$date       = $this->date_param( $request->get_param( 'date' ) );
		if ( ! $episode_id ) {
			return new WP_Error( 'ng_missing_episode', 'episode_id is required.', array( 'status' => 400 ) );
		}
		$counted = Net_Gain_Photo_Library::record_use( $id, $episode_id, $date );
		return rest_ensure_response( array( 'counted' => $counted, 'photo' => Net_Gain_Photo_Library::to_array( get_post( $id ) ) ) );
	}

	private function date_param( $value ) {
		return is_string( $value ) && preg_match( '/^\d{4}-\d{2}-\d{2}$/', $value ) ? $value : current_time( 'Y-m-d' );
	}
}
